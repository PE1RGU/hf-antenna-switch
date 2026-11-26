# D-217 designed corridor candidates (input for gen_rfboard_copper.py and the router keep-outs).
# Per straight RF segment at most ceil(nets/9) corridors of 1.5 to 6 mm, near the median of the present crossings.
# A corridor keeps END_T mm from a segment end that joins other RF copper (T, corner, crossing) and END_P mm from a pad end,
# and OTHER_KEEP mm from every other RF segment that is not collinear with it.
import re,fnmatch,math,json,sys
s=open('rf-board.kicad_pcb').read()
segs=re.findall(r'\(segment\s+\(start ([\d.\-]+) ([\d.\-]+)\)\s+\(end ([\d.\-]+) ([\d.\-]+)\)\s+\(width ([\d.]+)\)\s+(?:\(locked [^)]*\)\s+)?\(layer "([^"]+)"\)\s+\(net (?:\d+ )?"?([^")]*)"?\)',s)
RF=("/ANT*","*TXBUS","*RXBUS","/R?_RADIO","/R?_EXP","/A?_ANTENNA","*/PORT","*/PARK")
isrf=lambda n:any(fnmatch.fnmatchcase(n,p) for p in RF)
O=20
rf=[(float(a)-O,float(b)-O,float(c)-O,float(d)-O,L[0],n) for a,b,c,d,w,L,n in segs if isrf(n) and L in('F.Cu','B.Cu')]
lg=[(float(a)-O,float(b)-O,float(c)-O,float(d)-O,L,n) for a,b,c,d,w,L,n in segs if not isrf(n) and L in('In2.Cu','In3.Cu')]
def ix(p,q):
    (x1,y1,x2,y2),(x3,y3,x4,y4)=p,q
    den=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
    if abs(den)<1e-12: return None
    t=((x1-x3)*(y3-y4)-(y1-y3)*(x3-x4))/den; u=-((x1-x2)*(y1-y3)-(y1-y2)*(x1-x3))/den
    if 0<t<1 and 0<u<1: return t
def dps(px,py,q):
    dx,dy=q[2]-q[0],q[3]-q[1]; l2=dx*dx+dy*dy; t=max(0,min(1,((px-q[0])*dx+(py-q[1])*dy)/l2)) if l2 else 0
    return math.hypot(px-q[0]-t*dx,py-q[1]-t*dy)
def colin(q,r):
    return abs((q[2]-q[0])*(r[3]-r[1])-(q[3]-q[1])*(r[2]-r[0]))<1e-6 and dps(q[0],q[1],(r[0],r[1],r[0]+(r[2]-r[0])*1e3,r[1]+(r[3]-r[1])*1e3))<1e-3
PITCH, MARG, LMIN, LMAX, END_T, END_P, OTHER_KEEP, NPC, FULL = 0.7, 1.25, 1.5, 6.0, 3.5, 1.5, 3.5, 5, True
cor=[]; drop=[]
for r in rf:
    x1,y1,x2,y2,L,n=r; Ls=math.hypot(x2-x1,y2-y1); ux,uy=(x2-x1)/Ls,(y2-y1)/Ls
    hits=sorted((ix(r[:4],a[:4])*Ls,a[5]) for a in lg if ix(r[:4],a[:4]) is not None)
    if not hits: continue
    others=[q for q in rf if q is not r and not (q[5]==n and colin(q,r))]
    def joined(px,py): return any(dps(px,py,q)<0.01 for q in others)
    e0=END_T if joined(x1,y1) else END_P; e1=END_T if joined(x2,y2) else END_P
    def ok(a,b):
        pts=[(x1+ux*t,y1+uy*t) for t in (a,(a+b)/2,b)]
        return all(dps(px,py,q)>=OTHER_KEEP for q in others for px,py in pts)
    nets=sorted({h[1] for h in hits}); k=math.ceil(len(nets)/NPC)
    seg_done=[]
    for g in [hits[i*len(hits)//k:(i+1)*len(hits)//k] for i in range(k)]:
        nn={h[1] for h in g}; ln=LMAX if FULL else min(LMAX,max(2.5,len(nn)*PITCH+2*MARG)); med=g[len(g)//2][0]; best=None
        while ln>=LMIN-1e-9 and best is None:
            cands=[e0+ln/2+0.1*i for i in range(int((Ls-e0-e1-ln)/0.1)+1)] if Ls-e0-e1>=ln else []
            for m in sorted(cands,key=lambda m:abs(m-med)):
                if ok(m-ln/2,m+ln/2): best=m; break
            if best is None: ln-=0.5
        if best is None: drop.append((n.split('/')[-1],L,round(Ls,1),sorted(nn))); continue
        a,b=best-ln/2,best+ln/2
        for c0,c1 in seg_done:                     # two corridors on one segment: no overlap (r3)
            if a<c1 and c0<b: a,b=(max(a,c1),b) if best>(c0+c1)/2 else (a,min(b,c0))
        seg_done.append((a,b)); ln=b-a
        cor.append(dict(layer=L,net=n,p0=[round(x1+ux*a,3),round(y1+uy*a,3)],p1=[round(x1+ux*b,3),round(y1+uy*b,3)],len=round(ln,2),nets=sorted(nn)))
tot=sum(c['len'] for c in cor); rfl=sum(math.hypot(r[2]-r[0],r[3]-r[1]) for r in rf)
print(len(cor),'corridors, total',round(tot),'mm =',round(100*tot/rfl,1),'% of',round(rfl),'mm RF; longest',max(c['len'] for c in cor))
print('segments with crossings but no corridor:',len(drop))
for d in drop: print('  ',d)
json.dump(cor,open(sys.argv[1],'w'),indent=0)
