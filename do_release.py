"""
Full release automation: build → zip → commit → tag → push → GitHub release.

Usage:
    python do_release.py <version> [release notes line] [release notes line] ...

Examples:
    python do_release.py 1.3.0
    python do_release.py 1.3.0 "- Fix: something" "- Add: something else"

If no release notes are provided, they are generated from git log since the last tag.
"""

import subprocess
import sys
import os
import tempfile

KOFI = "If this saved you some time, feel free to buy me a coffee ☕\n[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/jasbob)"
ZIP = "lol-autouploader.zip"


def run(cmd, **kwargs):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"FAILED: {cmd}\n{result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python do_release.py <version> [note] [note] ...")
        print("  e.g. python do_release.py 1.3.0 '- Fix: bad matching'")
        sys.exit(1)

    version = sys.argv[1].lstrip("v")
    tag = f"v{version}"
    extra_notes = sys.argv[2:]

    # Check for uncommitted changes
    dirty = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True).stdout.strip()
    if dirty:
        print("Uncommitted changes detected — committing them now...")
        run("git add -A")
        run(f'git commit -m "v{version} release prep\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"')

    # Build
    print(f"\n=== Building v{version} ===")
    result = subprocess.run("make build", shell=True)
    if result.returncode != 0:
        sys.exit(1)

    # Package zip
    print("\n=== Packaging zip ===")
    result = subprocess.run("python package_release.py", shell=True)
    if result.returncode != 0:
        sys.exit(1)

    # Build release notes
    if extra_notes:
        notes_body = "\n".join(extra_notes)
    else:
        # Auto-generate from git log since last tag
        last_tag = subprocess.run(
            "git describe --tags --abbrev=0 2>nul", shell=True, capture_output=True, text=True
        ).stdout.strip()
        if last_tag:
            log = run(f"git log {last_tag}..HEAD --pretty=format:\"- %s\"")
        else:
            log = run('git log --pretty=format:"- %s"')
        notes_body = log if log else "- Minor improvements"

    notes = f"{notes_body}\n\n---\n\n{KOFI}"

    # Tag and push
    print(f"\n=== Tagging {tag} and pushing ===")
    run(f'git tag {tag}')
    run("git push")
    run("git push --tags")

    # Create GitHub release — write notes to a file to avoid shell escaping issues
    print(f"\n=== Creating GitHub release {tag} ===")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(notes)
        notes_file = f.name
    try:
        run(f'gh release create {tag} {ZIP} --title "{tag}" --notes-file "{notes_file}"')
    finally:
        os.unlink(notes_file)

    print(f"\nDone! https://github.com/jason-tung/lol-autouploader/releases/tag/{tag}")


if __name__ == "__main__":
    main()
