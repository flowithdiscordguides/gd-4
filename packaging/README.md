# Packaging GitDesk

The repository includes `.github/workflows/build-app.yml` for desktop build artifacts.

## Workflow

1. Push a tag like `v0.1.0`, or run **Build GitDesk App** manually from GitHub Actions.
2. Download the artifact matching the target computer:
   - `GitDesk-macOS-arm64` contains `GitDesk-macOS-arm64.dmg` for Apple Silicon Macs.
   - `GitDesk-macOS-x86_64` contains `GitDesk-macOS-x86_64.dmg` for Intel Macs.
   - `GitDesk-Windows-x64` and `GitDesk-Linux-x64` contain the other desktop builds.
3. Keep the architecture label in the macOS filename when distributing or attaching the DMG to a release.
4. For tag pushes, review the generated draft GitHub Release before publishing it.
5. Smoke test the artifact on its target operating system before making the release public.

The workflow uses PyInstaller in GitHub Actions and builds each macOS artifact on its matching native runner.
Each macOS job stages only its matching WebUI native library before PyInstaller runs: `arm64` uses
`webui-macos-clang-arm64`, while Intel `x86_64` uses WebUI's `webui-macos-clang-x64` folder. This prevents the
opposite CPU architecture from entering the signed app under `Contents/Frameworks`.
The Intel job also imports cryptography before packaging and asks dyld which `libssl.3.dylib` and
`libcrypto.3.dylib` made that import succeed. CI stages that co-located pair, thins it to `x86_64`, normalizes its
bundle-local links, supplies it to PyInstaller explicitly, and reinstalls the same bytes into the finished app before
signing. This prevents an older same-named OpenSSL library from replacing the library required by cryptography.
Before creating the DMG, CI runs persistence, keyring, and Local Mode regression tests, then launches the frozen binary
in non-UI self-check mode. The bundle verifier requires the executable and sole bundled WebUI dylib to contain exactly
the matrix entry's `arm64` or `x86_64` architecture, GitDesk's stable bundle identifier, all protected-folder privacy
descriptions, a generated build version, one shared LocalApp metadata directory, the stable `GitDesk` operating-system
credential service, and the in-app Guide asset.
Every matrix target packages the read-only `Shared-Resources/categories` catalog under the same bundle path. The
retired `AI-Skills` directory is neither a build input nor a runtime fallback.
For Intel, verification additionally requires an x86_64-only OpenSSL pair and confirms that the final bundled libssl
exports `_SSL_get0_group_name`, the API cryptography 49 needs during native-module initialization.
The self-check validates configuration only; it never reads a PAT or opens a Keychain item.
If the packaged process fails, the verifier reads any generated JSON report before evaluating its exit status and
names the exact failed field. Failures before report creation include the packaged process's bounded stdout and stderr
in the Actions error so native-loader and frozen-import problems are not reduced to an unexplained status code.

GitDesk stores GitHub PATs in macOS Keychain under the stable `GitDesk` service and one
`github-token:<resource-owner>` account per PAT profile. Bootstrap and account-list rendering use only a non-secret
configured-state marker and never read those Keychain items. GitDesk opens only the selected profile's item when a Git
or GitHub operation first needs it, then reuses the authorized PAT from volatile process memory for that session.
Settings, repository records, document and Media registries, Shared Resource manifests, Sync Ignore rules, Local
Activity, and Backup state remain non-secret JSON in the platform configuration directory. Editable Shared Resources
use the platform user-data directory. Both locations are outside the source checkout, and private writes reject a
repository-local destination.

macOS owns and validates the password dialog; the application does not receive the entered Keychain password. The
`Allow` or `Always Allow` result applies to the exact credential request macOS is presenting. A different saved PAT is
a different Keychain item, and a newly rebuilt ad-hoc-signed app may require fresh approval when an item is first used.

The stable `com.xander.gitdesk` bundle identifier identifies the app, while Keychain trust also evaluates its code
signature. Signing and notarization stay as separate release steps, so a rebuilt ad-hoc-signed test app can still need
fresh Keychain approval. For a clean Documents-folder prompt test, reset macOS's remembered decision before opening
the new build:

```bash
tccutil reset SystemPolicyDocumentsFolder com.xander.gitdesk
```

After installing the DMG, verify the app bundle and inspect its privacy metadata:

```bash
codesign --verify --deep --strict --verbose=2 "/Applications/GitDesk.app"
plutil -p "/Applications/GitDesk.app/Contents/Info.plist"
```
