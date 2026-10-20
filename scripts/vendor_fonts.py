"""Vendor pinned OFL webfonts; runtime pages never contact an external font service."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "noto-sans-sc": ("5.3.1", "UB96JJ17HyD5ehEU7Em0hDdh7fvTMB4B4Hzmq5c4QaNwwSLqTrdM2S+coySeBqCkXwh0DxqXT0b0wMrmzorFpQ=="),
    "noto-serif-sc": ("5.3.1", "aIHcBaL13QctVaJFeT6wqfgO9Rq/cNtD5g2ob4ze59fYPYwacGthnIrHBe83kDpMEB/k6VGtGc6fS99RImcoSQ=="),
    "noto-sans-mono": ("5.3.0", "EgozyWG4nG2U1OT+zfdyHP1L8O0fUFMUBOilVF9urTshqIdfeGV9/FUQxaNHdPvHtV1cQCs1Ql0W1q93SiPK2w=="),
}


def main():
    web = ROOT / "src/mvp/web"
    cache = ROOT / "data/font-sources"
    cache.mkdir(parents=True, exist_ok=True)
    css = ["/* Pinned OFL fonts. Unicode subsets are fetched from this site only when needed. */\n",
           ":root { --font-sans: 'Noto Sans SC Variable', sans-serif; --font-serif: 'Noto Serif SC Variable', serif; --font-mono: 'Noto Sans Mono Variable', 'Noto Sans SC Variable', monospace; }\n"]
    manifest = []
    for name, (version, expected) in PACKAGES.items():
        url = f"https://registry.npmjs.org/@fontsource-variable/{name}/-/{name}-{version}.tgz"
        archive = cache / f"{name}.tgz"
        data = archive.read_bytes() if archive.exists() else urllib.request.urlopen(url, timeout=45).read()
        integrity = base64.b64encode(hashlib.sha512(data).digest()).decode()
        if integrity != expected:
            raise ValueError(f"Font archive integrity mismatch: {name}")
        archive.write_bytes(data)
        target = web / "fonts" / name
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            rules = tar.extractfile("package/wght.css").read().decode()
            files = sorted(set(re.findall(r"\./files/([\w.-]+\.woff2)", rules)))
            for filename in files:
                (target / filename).write_bytes(tar.extractfile(f"package/files/{filename}").read())
            license_name = next(m.name for m in tar.getmembers() if m.name in ("package/LICENSE", "package/OFL.txt"))
            (target / "OFL.txt").write_bytes(tar.extractfile(license_name).read())
        rules = rules.replace("./files/", f"/static/fonts/{name}/").replace("font-display: swap", "font-display: block")
        css.append(rules)
        manifest.append({"package": f"@fontsource-variable/{name}", "version": version, "license": "OFL-1.1",
                         "source": url, "integrity": "sha512-" + integrity, "files": files})
    (web / "fonts.css").write_text("\n".join(css), encoding="utf-8")
    (web / "fonts/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Vendored {sum(len(p['files']) for p in manifest)} WOFF2 subsets; licenses retained.")


if __name__ == "__main__":
    main()
