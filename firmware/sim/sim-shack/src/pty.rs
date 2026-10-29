//! Real-time run on a pseudo-terminal. The pty is the USB port of the simulated
//! shack interface. This terminal (stdin) controls the outside world.

use nix::fcntl::{FcntlArg, OFlag, fcntl};
use nix::pty::openpty;
use nix::sys::termios::{SetArg, cfmakeraw, tcgetattr, tcsetattr};
use nix::unistd::{read, ttyname, write};
use sim_shack::ShackSim;
use std::io::BufRead;
use std::sync::mpsc;
use std::time::{Duration, Instant};

const HELP: &str = "\
outside world (type here, Enter):
  reset              press and release the RESET button
  kill on|off        KILL switch pressed / released
  cable on|off       Cat6 intact / cut
  power on|off       13.8 V on / off
  radio R1|R2|R3 on|off   radio TX sense (radio transmits)
  box mute on|off    box stops / resumes answering
  status             board signals
  shot <file.png>    save the display (3x)
  quit";

pub fn run() {
    let pty = openpty(None, None).expect("openpty");
    let mut t = tcgetattr(&pty.slave).expect("tcgetattr");
    cfmakeraw(&mut t);
    tcsetattr(&pty.slave, SetArg::TCSANOW, &t).expect("tcsetattr");
    fcntl(&pty.master, FcntlArg::F_SETFL(OFlag::O_NONBLOCK)).expect("non-blocking");
    let path = ttyname(&pty.slave).expect("ttyname");

    println!("Simulated shack interface on {}", path.display());
    println!("Connect, for example:  screen {} 115200", path.display());
    println!("{HELP}\n");

    let (tx, rx) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        for line in std::io::stdin().lock().lines().map_while(Result::ok) {
            if tx.send(line).is_err() {
                break;
            }
        }
    });

    let mut s = ShackSim::new();
    let start = Instant::now();
    let mut sent = 0;
    let mut buf = [0u8; 256];
    loop {
        // Host bytes in.
        if let Ok(n) = read(&pty.master, &mut buf)
            && n > 0
        {
            let text = String::from_utf8_lossy(&buf[..n]).into_owned();
            s.board.borrow_mut().host_send(&text);
        }
        // Outside world.
        while let Ok(cmd) = rx.try_recv() {
            if !world(&mut s, cmd.trim()) {
                return;
            }
        }
        // Simulated time follows the wall clock.
        let target = start.elapsed().as_millis() as u64;
        while s.now() < target {
            s.step();
        }
        // Lines out.
        while sent < s.host_lines.len() {
            let line = format!("{}\r\n", s.host_lines[sent].1);
            let _ = write(&pty.master, line.as_bytes());
            sent += 1;
        }
        std::thread::sleep(Duration::from_millis(1));
    }
}

/// One outside-world command. Returns false on quit.
fn world(s: &mut ShackSim, cmd: &str) -> bool {
    let w: Vec<&str> = cmd.split_whitespace().collect();
    let on = |x: &str| x == "on";
    let mut b = s.board.borrow_mut();
    match w.as_slice() {
        ["quit"] => return false,
        ["reset"] => {
            drop(b);
            s.press_reset();
            println!("RESET pressed");
            return true;
        }
        ["kill", v] => b.set_env(|e| e.kill_pressed = on(v)),
        ["cable", v] => b.set_env(|e| e.cable_ok = on(v)),
        ["power", v] => b.set_env(|e| e.power = on(v)),
        ["radio", r, v] => {
            let Some(i) = ["R1", "R2", "R3"]
                .iter()
                .position(|x| x.eq_ignore_ascii_case(r))
            else {
                println!("radio R1, R2 or R3");
                return true;
            };
            b.set_env(|e| e.radio_tx[i] = on(v));
        }
        ["box", "mute", v] => {
            drop(b);
            s.boxs.mute = on(v);
            println!("box mute {v}");
            return true;
        }
        ["shot", path] => {
            drop(b);
            s.save_screen(std::path::Path::new(path), 3);
            println!("display saved to {path}");
            return true;
        }
        ["status"] => {
            println!("{:?}", b.signals());
            return true;
        }
        [] => return true,
        _ => {
            println!("{HELP}");
            return true;
        }
    }
    println!("{cmd}: done");
    true
}
