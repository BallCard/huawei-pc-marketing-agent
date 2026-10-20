"""Apply one audited readiness correction to the pinned upstream source."""
import sys
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
path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
