"""Apply one audited readiness correction to the pinned upstream source."""
import sys
import shutil
from pathlib import Path

root = Path(sys.argv[1])
path = root / "cmd/gptweb2api/main.go"
source = path.read_text(encoding="utf-8")
old = 'AuthConfigured:                 authMode != "none",'
new = '''AuthConfigured: authMode != "none" && func() bool {
            if credentials == nil { return true }
            snapshot, err := credentials.Current(context.Background())
            return err == nil && strings.TrimSpace(snapshot.AccessToken) != ""
        }(),'''
if old not in source:
    raise SystemExit("Pinned gateway source changed; readiness patch not applied")
source = source.replace(old, new, 1)
if 'Handler:           handler,' not in source:
    raise SystemExit("Pinned HTTP server changed; route restriction not applied")
source = source.replace('Handler:           handler,', 'Handler:           posterOnly(handler),', 1)
path.write_text(source, encoding="utf-8", newline="\n")
for name in ("poster_only.go", "poster_only_test.go"):
    shutil.copyfile(Path(__file__).parent/name, root/"cmd/gptweb2api"/name)
path = root/"internal/chatgpt/client.go"
source = path.read_text(encoding="utf-8")
needle = '\tif strings.TrimSpace(in.Model) == "" {\n'
if source.count(needle) != 1:
    raise SystemExit("Pinned image preparation changed; input filter not applied")
addition = '''\tif len(images) != 0 {
        inputs := make(map[string]bool, len(images))
        for _, image := range images { inputs[image.fileID] = true }
        emit = withoutInputImages(emit, inputs)
    }
'''
path.write_text(source.replace(needle, addition+needle, 1),encoding="utf-8",newline="\n")
for name in ("poster_asset_filter.go", "poster_asset_filter_test.go"):
    shutil.copyfile(Path(__file__).parent/name,root/"internal/chatgpt"/name)
