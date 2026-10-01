# Review of [`settings.json`](file:///c:/Codes/DeepSea/src/settings.json)

Cross-referenced with [`start.py`](file:///c:/Codes/DeepSea/src/start.py), [`gh.py`](file:///c:/Codes/DeepSea/src/gh.py), and [`fs.py`](file:///c:/Codes/DeepSea/src/fs.py).

---

## 🔴 Errors / Bugs

### 1. `nxshell` regex anchoring mismatch (line 552)

```json
"regex": [".*NX-Shell.*\\.nro$"]
```

The `.*` prefix makes the `^` anchor meaningless by design, so this matches filenames **containing** `NX-Shell` anywhere (e.g. `v4.01-NX-Shell-thing.nro`). But the `move` step on [line 564](file:///c:/Codes/DeepSea/src/settings.json#L564) hardcodes the exact filename `NX-Shell.nro`:

```json
"move": ["NX-Shell.nro", "switch/NX-Shell/NX-Shell.nro"]
```

If the release asset is named something like `NX-Shell-v4.01.nro`, the regex would match and download it, but the `move` step would fail because no file named exactly `NX-Shell.nro` exists. Either:
- **Tighten the regex** to `^NX-Shell\\.nro$` (like `jksv`, `goldleaf`, `checkpoint` do), or
- **Use a glob/wildcard** in the move step argument.

### 2. `checkpoint` same issue (line 587)

```json
"regex": [".*Checkpoint.*\\.nro$"]
```

Move step on [line 599](file:///c:/Codes/DeepSea/src/settings.json#L599) expects exactly `Checkpoint.nro`. Same mismatch risk as `nxshell` above. The actual Checkpoint release assets are named `Checkpoint.nro`, so the anchored regex `^Checkpoint\\.nro$` would be safer and consistent with similar modules.

### 3. `sysftpd` — hardcoded default credentials (lines 397, 405)

```json
"user:=deepsea"
"password:=secretpass"
```

These are baked into the config template that ships in the zip. If this ends up on users' SD cards, every DeepSea user has the same FTP credentials. This isn't a JSON error, but it's a **security concern** worth flagging.

---

## 🟡 Potential Issues

### 4. `edizon-ovl` — repo may be stale (line 206)

```json
"repo": "proferabg/EdiZon-Overlay"
```

The original EdiZon-Overlay was under `WerWolv/EdiZon-Overlay`. If `proferabg` is a fork, verify it's still actively maintained and publishing releases. If it has no releases, `downloadReleaseAssets` will silently fail and the module will be skipped.

### 5. `awoo` — repo archived/unmaintained (line 571)

```json
"repo": "Huntereb/Awoo-Installer"
```

Awoo-Installer has been archived for a long time. `get_latest_release()` may still succeed if historical releases exist, but no new versions will ever appear. Consider whether this module should remain in the package.

### 6. `aioupdater` — repo archived (line 172)

```json
"repo": "HamletDuFromage/aio-switch-updater"
```

aio-switch-updater has been archived. Same concern as Awoo.

### 7. `teslamenu` points to Ultrahand, not Tesla (line 473)

```json
"repo": "ppkantorski/Ultrahand-Overlay"
```

The module is called `teslamenu` but downloads from `Ultrahand-Overlay`. The regex looks for `ovlmenu.ovl`, which is the **Tesla Menu** filename convention. Verify that Ultrahand's releases still produce `ovlmenu.ovl` as an asset name — Ultrahand may ship as `ovlmenu.ovl` or may have renamed it. If it did rename, the regex would match nothing.

---

## 🟢 Improvements

### 8. Redundant `create_dir` for `switch/.overlays` (lines 459, 480)

Both `ovlsysmodules` and `teslamenu` create `switch/.overlays`. This works fine (it's idempotent via `exist_ok=True`), but if you ever add more overlay modules you'll keep duplicating it. Consider whether a shared pre-step or a convention could avoid the repetition.

### 9. Inconsistent `boot2.flag` deletion pattern

Several sysmodules delete their `boot2.flag` so they don't auto-start at boot:
| Module | Title ID |
|---|---|
| `emuiibo` | `0100000000000352` |
| `sysclk` | `00FF0000636C6BFF` |
| `syscon` | `690000000000000D` |
| `sysftpd` | `420000000000000E` |
| `ldn_mitm` | `4200000000000010` |
| `missioncontrol` | `010000000000bd00` |

But `nxovlloader` (which also installs into `atmosphere/contents/`) does **not** delete its `boot2.flag` — presumably intentionally, since the overlay loader must auto-start. Just verify this is deliberate and consistent with your intent.

### 10. No `toolbox.json` for several sysmodules

`sysclk` and `ldn_mitm` create a `toolbox.json` (so they appear in Tesla/Ultrahand's sysmodule toggle overlay). But `syscon`, `sysftpd`, `emuiibo`, `missioncontrol`, and `nxovlloader` do **not**. If users are expected to toggle those via the overlay, they'll be missing from the list. Consider adding `toolbox.json` entries for consistency.

### 11. Consider adding a JSON schema

With 648 lines and a growing module list, a [JSON Schema](https://json-schema.org/) definition would:
- Catch typos in step names (`"extact"` instead of `"extract"`)
- Enforce required fields (`repo`, `regex`, `steps`)
- Validate argument counts per step type
- Enable IDE autocompletion

### 12. `releaseVersion` — manual maintenance (line 2)

```json
"releaseVersion": "1.12-atmo-09-30-26"
```

This is embedded in the filename of the output zip. If it gets out of sync with the actual release, the artifact is mislabeled. Consider generating it from git tags or CI env variables instead.

---

## ✅ What looks good

- **JSON is valid** — no syntax errors, well-formatted with consistent 4-space indentation.
- **Module list matches package list** — every name in `packages[0].modules` has a corresponding key in `moduleList`. No orphaned or missing entries.
- **Regex escaping is correct** — double-escaped `\\.` is the right way to escape a literal dot in a JSON-embedded regex.
- **Step arguments match what `fs.py` expects** — argument counts for `extract(1)`, `copy(2)`, `move(2)`, `create_dir(1)`, `create_file(2)`, `replace_content(3)`, `delete(1)` all look correct.
- **`releaseTag` used correctly** — `nxdumptool` pins to `"rewrite-prerelease"`, which `gh.py` handles via `get_release(tag)` rather than `get_latest_release()`.
