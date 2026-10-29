//! Real-time run on a pseudo-terminal (Unix only). The pty is the USB port of the
//! simulated shack interface; this terminal (stdin) controls the outside world.
//! The terminal UI (`sim-shack`, all systems) does the same with the display shown.

use nix::fcntl::{FcntlArg, OFlag, fcntl};
use nix::pty::openpty;
use nix::sys::termios::{SetArg, cfmakeraw, tcgetattr, tcsetattr};
use nix::unistd::{read, ttyname, write};
use sim_shack::{ShackSim, WORLD_HELP};
use std::io::BufRead;
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub fn run(mut s: ShackSim) {
    let pty = openpty(None, None).expect("openpty");
    let mut t = tcgetattr(&pty.slave).expect("tcgetattr");
    cfmakeraw(&mut t);
    tcsetattr(&pty.slave, SetArg::TCSANOW, &t).expect("tcsetattr");
    fcntl(&pty.master, FcntlArg::F_SETFL(OFlag::O_NONBLOCK)).expect("non-blocking");
    let path = ttyname(&pty.slave).expect("ttyname");

    println!("Simulated shack interface on {}", path.display());
    println!("Connect, for example:  screen {} 115200", path.display());
    println!("{WORLD_HELP}\n(type here, Enter; quit to stop)\n");

    let (tx, rx) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        for line in std::io::stdin().lock().lines().map_while(Result::ok) {
            if tx.send(line).is_err() {
                break;
            }
        }
    });

    let start = Instant::now();
    let mut sent = 0;
    let mut buf = [0u8; 256];
    loop {
        if let Ok(n) = read(&pty.master, &mut buf)
            && n > 0
        {
            let text = String::from_utf8_lossy(&buf[..n]).into_owned();
            s.board.borrow_mut().host_send(&text);
        }
        while let Ok(cmd) = rx.try_recv() {
            match cmd.trim() {
                "quit" => return,
                "" => {}
                c => match s.world(c) {
                    Ok(m) => println!("{m}"),
                    Err(h) => println!("{h}"),
                },
            }
        }
        let target = start.elapsed().as_millis() as u64;
        while s.now() < target {
            s.step();
        }
        while sent < s.host_lines.len() {
            let line = format!("{}\r\n", s.host_lines[sent].1);
            let _ = write(&pty.master, line.as_bytes());
            sent += 1;
        }
        std::thread::sleep(Duration::from_millis(1));
    }
}
