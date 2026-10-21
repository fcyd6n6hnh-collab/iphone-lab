"""Pull C strings and Swift/ObjC name sections for one image out of an iOS dyld_shared_cache
without needing the (lzbitmap-compressed) .dyldlinkedit/.symbols subcaches. Writes a raw Mach-O-ish
text slice too, so REA/rizin can inspect it.  usage: dsc_strings.py CACHE_DIR ImageName OUTDIR"""
import struct, sys, os, glob
d, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
files = sorted(glob.glob(os.path.join(d, 'dyld_shared_cache_arm64e*')))
maps = []
for f in files:
    h = open(f, 'rb').read(0x200)
    if not h.startswith(b'dyld_v1') or os.path.getsize(f) < 0x10000 or f.endswith(('symbols', 'dyldlinkedit')): continue
    mo, mc = struct.unpack_from('<II', h, 0x10)
    raw = open(f, 'rb').read(mo + mc * 32)
    for i in range(mc):
        a, s, fo, _, _ = struct.unpack_from('<QQQII', raw, mo + i * 32)
        maps.append((a, s, fo, f))
def read(addr, n):
    for a, s, fo, f in maps:
        if a <= addr < a + s:
            with open(f, 'rb') as fh: fh.seek(fo + addr - a); return fh.read(min(n, a + s - addr))
    raise KeyError(hex(addr))
main = open(os.path.join(d, 'dyld_shared_cache_arm64e'), 'rb').read()
io, ic = struct.unpack_from('<II', main, 0x1c0)
target = None
for i in range(ic):
    addr, _, _, po, _ = struct.unpack_from('<QQQII', main, io + i * 32)
    p = main[po:main.index(b'\0', po)].decode()
    if p.endswith('/' + name): target = (addr, p); break
if not target: sys.exit('image not found')
addr, path = target
hdr = read(addr, 0x8000)
ncmds, sz = struct.unpack_from('<II', hdr, 16)
off = 32; secs = {}
for _ in range(ncmds):
    cmd, cs = struct.unpack_from('<II', hdr, off)
    if cmd == 0x19:
        seg = hdr[off+8:off+24].rstrip(b'\0').decode(); nsect = struct.unpack_from('<I', hdr, off + 64)[0]
        for k in range(nsect):
            so = off + 72 + k * 80
            sect = hdr[so:so+16].rstrip(b'\0').decode(); saddr, ssize = struct.unpack_from('<QQ', hdr, so + 32)
            secs[f'{seg},{sect}'] = (saddr, ssize)
    off += cs
print(path, hex(addr), {k: hex(v[1]) for k, v in secs.items() if k.startswith('__TEXT')})
allstr = set()
for k in ('__TEXT,__cstring', '__TEXT,__objc_methname', '__TEXT,__objc_classname', '__TEXT,__swift5_reflstr', '__TEXT,__oslogstring'):
    if k in secs:
        b = read(*secs[k])
        for s in b.split(b'\0'):
            try: t = s.decode()
            except UnicodeDecodeError: continue
            if len(t) >= 3: allstr.add(t)
open(os.path.join(out, name + '.strings.txt'), 'w').write('\n'.join(sorted(allstr)))
# also dump the __TEXT segment bytes (header + code + strings) for REA/rizin
ta, ts = secs.get('__TEXT,__text', (0, 0))
seg_end = max(a + s for k, (a, s) in secs.items() if k.startswith('__TEXT'))
open(os.path.join(out, name + '.text.bin'), 'wb').write(read(addr, seg_end - addr))
print(len(allstr), 'strings')
