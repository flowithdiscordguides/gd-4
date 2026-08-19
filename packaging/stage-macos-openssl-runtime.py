"""Stage and install the OpenSSL runtime pair already proven to load with cryptography on macOS."""

from __future__ import annotations

# Standard-library modules inspect dyld state, normalize Mach-O links, and copy the verified runtime pair.
import ctypes
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


# Resolve generated staging output from this script so every workflow command remains repository-relative.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_ROOT = PROJECT_ROOT / "build" / "openssl-runtime"

# OpenSSL keeps SSL and cryptographic primitives in separate libraries that must come from the same build.
OPENSSL_RUNTIME_FILENAMES = ("libssl.3.dylib", "libcrypto.3.dylib")
REQUIRED_SSL_SYMBOL = "_SSL_get0_group_name"
SUPPORTED_ARCHITECTURES = {"arm64", "x86_64"}


# Runs one Apple binary tool and stops with its stderr when a Mach-O operation cannot be completed safely.
def run_apple_tool(arguments: list[str]) -> str:
    """Run one Apple command, returning stdout or raising SystemExit with diagnostic output."""

    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise SystemExit(f"Unable to prepare the macOS OpenSSL runtime: {details}")
    return result.stdout


# Imports cryptography's native module before dyld enumeration so its working OpenSSL images are loaded.
def load_cryptography_extension() -> Path:
    """Import cryptography's Rust binding and return the native extension path selected by Python."""

    module = importlib.import_module("cryptography.hazmat.bindings._rust")
    module_path = Path(str(getattr(module, "__file__", ""))).resolve()
    if not module_path.is_file():
        raise SystemExit("Cryptography's loaded Rust extension path could not be resolved.")
    return module_path


# Reads dyld's loaded-image table so staging uses the libraries that made the successful import possible.
def loaded_image_paths() -> list[Path]:
    """Return resolved filesystem paths for every Mach-O image loaded in the current process."""

    process = ctypes.CDLL(None)
    image_count = process._dyld_image_count
    image_count.argtypes = []
    image_count.restype = ctypes.c_uint32
    image_name = process._dyld_get_image_name
    image_name.argtypes = [ctypes.c_uint32]
    image_name.restype = ctypes.c_char_p

    paths = []
    # dyld is authoritative here because an @rpath load command alone does not reveal the file actually selected.
    for image_index in range(image_count()):
        encoded_path = image_name(image_index)
        if encoded_path:
            paths.append(Path(os.fsdecode(encoded_path)).resolve())
    return paths


# Selects exactly one co-located SSL/crypto pair from the images used by the successful cryptography import.
def loaded_openssl_pair() -> dict[str, Path]:
    """Return the loaded OpenSSL 3 pair, rejecting missing, ambiguous, or mixed-installation libraries."""

    extension_path = load_cryptography_extension()
    candidates = {
        filename: [path for path in loaded_image_paths() if path.name == filename and path.is_file()]
        for filename in OPENSSL_RUNTIME_FILENAMES
    }
    ambiguous = [filename for filename, paths in candidates.items() if len(paths) != 1]
    if ambiguous:
        details = ", ".join(f"{filename}={len(candidates[filename])}" for filename in ambiguous)
        raise SystemExit(
            f"Cryptography loaded from {extension_path}, but its OpenSSL pair was not unique ({details})."
        )

    pair = {filename: paths[0] for filename, paths in candidates.items()}
    if len({path.parent for path in pair.values()}) != 1:
        raise SystemExit("Cryptography loaded libssl and libcrypto from different runtime directories.")
    return pair


# Reads every architecture in a Mach-O file so staging cannot cross-contaminate the two macOS builds.
def binary_architectures(binary_path: Path) -> set[str]:
    """Return every architecture reported by lipo for one OpenSSL dynamic library."""

    return set(run_apple_tool(["lipo", "-archs", str(binary_path)]).split())


# Confirms the selected SSL library exports the exact API missing from the failed Intel app bundle.
def verify_required_ssl_symbol(ssl_path: Path) -> None:
    """Require the selected libssl to export the symbol cryptography 49 uses during initialization."""

    symbols = set(run_apple_tool(["nm", "-gU", str(ssl_path)]).split())
    if REQUIRED_SSL_SYMBOL not in symbols:
        raise SystemExit(f"The loaded {ssl_path} does not export {REQUIRED_SSL_SYMBOL}.")


# Extracts one native architecture and normalizes local OpenSSL links for the self-contained app bundle.
def stage_binary(source_path: Path, destination_path: Path, expected_architecture: str) -> None:
    """Copy or thin one loaded dylib into staging, then give it a bundle-local Mach-O identity."""

    architectures = binary_architectures(source_path)
    if expected_architecture not in architectures:
        found = " ".join(sorted(architectures)) or "unknown"
        raise SystemExit(f"{source_path.name} lacks {expected_architecture}; found: {found}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if architectures == {expected_architecture}:
        shutil.copy2(source_path, destination_path)
    else:
        run_apple_tool(
            ["lipo", str(source_path), "-thin", expected_architecture, "-output", str(destination_path)]
        )
    run_apple_tool(["install_name_tool", "-id", f"@rpath/{source_path.name}", str(destination_path)])


# Repoints libssl at the staged libcrypto so neither library can escape to a runner-specific Homebrew path.
def normalize_ssl_crypto_link(ssl_path: Path) -> None:
    """Rewrite libssl's OpenSSL 3 crypto dependency to the sibling library bundled under @rpath."""

    linked_libraries = []
    for line in run_apple_tool(["otool", "-L", str(ssl_path)]).splitlines()[1:]:
        linked_name = line.strip().split(" (compatibility version", maxsplit=1)[0]
        if Path(linked_name).name == "libcrypto.3.dylib":
            linked_libraries.append(linked_name)
    if len(linked_libraries) != 1:
        raise SystemExit("The staged libssl does not declare exactly one libcrypto.3.dylib dependency.")
    run_apple_tool(
        ["install_name_tool", "-change", linked_libraries[0], "@rpath/libcrypto.3.dylib", str(ssl_path)]
    )


# Creates the exact-architecture pair that PyInstaller receives as explicit binary input for the Intel job.
def stage_runtime(expected_architecture: str) -> Path:
    """Stage cryptography's working OpenSSL pair and return its architecture-specific directory."""

    if sys.platform != "darwin":
        raise SystemExit("OpenSSL runtime staging is supported only on macOS.")
    if expected_architecture not in SUPPORTED_ARCHITECTURES:
        raise SystemExit(f"Unsupported macOS architecture: {expected_architecture or 'empty'}")

    pair = loaded_openssl_pair()
    verify_required_ssl_symbol(pair["libssl.3.dylib"])
    destination_root = STAGING_ROOT / expected_architecture
    for filename, source_path in pair.items():
        stage_binary(source_path, destination_root / filename, expected_architecture)
    normalize_ssl_crypto_link(destination_root / "libssl.3.dylib")
    return destination_root


# Overwrites PyInstaller's colliding OpenSSL files before signing, making the verified pair authoritative.
def install_runtime(app_path: Path, expected_architecture: str) -> Path:
    """Install the staged OpenSSL pair into one generated app bundle and return its Frameworks directory."""

    source_root = STAGING_ROOT / expected_architecture
    frameworks_path = app_path / "Contents" / "Frameworks"
    if not frameworks_path.is_dir():
        raise SystemExit(f"The generated app Frameworks directory was not found: {frameworks_path}")

    for filename in OPENSSL_RUNTIME_FILENAMES:
        source_path = source_root / filename
        destination_path = frameworks_path / filename
        if not source_path.is_file() or not destination_path.exists():
            raise SystemExit(f"Cannot replace the packaged OpenSSL runtime file: {destination_path}")
        if destination_path.is_symlink():
            destination_path.unlink()
        shutil.copy2(source_path, destination_path)
        if binary_architectures(destination_path) != {expected_architecture}:
            raise SystemExit(f"Packaged {filename} is not exclusively {expected_architecture}.")
    verify_required_ssl_symbol(frameworks_path / "libssl.3.dylib")
    return frameworks_path


# Provides separate stage and install boundaries so the same proven bytes survive PyInstaller assembly.
def main(argv: list[str]) -> int:
    """Stage or install the OpenSSL pair requested by the GitHub Actions macOS build."""

    if len(argv) == 3 and argv[1] == "stage":
        staged_root = stage_runtime(argv[2])
        print(f"Staged OpenSSL runtime at {staged_root.relative_to(PROJECT_ROOT)}")
        return 0
    if len(argv) == 4 and argv[1] == "install":
        frameworks_path = install_runtime(Path(argv[2]), argv[3])
        print(f"Installed OpenSSL runtime in {frameworks_path}")
        return 0
    raise SystemExit(
        "Usage: python packaging/stage-macos-openssl-runtime.py "
        "<stage ARCHITECTURE|install APP_PATH ARCHITECTURE>"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
