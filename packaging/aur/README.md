# AUR package

`PKGBUILD` is a template: the release workflow fills in `@VERSION@` and `@SHA256@`, generates `.SRCINFO`
and pushes both to `ssh://aur@aur.archlinux.org/ghost-trader.git` after publishing the release's source to
the public mirror (`flak-daddy/ghost-trader-source`).

Secrets the workflow needs (repo Settings → Secrets and variables → Actions):
- `SOURCE_DEPLOY_KEY`: private SSH key whose public half is a **write** deploy key on `ghost-trader-source`.
- `AUR_SSH_KEY`: private SSH key whose public half is on your AUR account.

Without them the release still happens; the publish steps are skipped.

## Without an AUR account

`packaging/arch/PKGBUILD` builds from the public repo's git tag (the release workflow fills in the version when
it publishes). Anyone can install with:

    git clone https://github.com/flak-daddy/ghost-trader-source.git
    cd ghost-trader-source/packaging/arch && yay -Bi .
