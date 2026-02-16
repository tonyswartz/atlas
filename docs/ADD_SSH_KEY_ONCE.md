# One-time: Add SSH key so Cursor sync doesn't get stuck

Git push was hanging in Cursor because HTTPS credential prompt never appears there. This repo is now set to use **SSH** for GitHub.

**Do this once:**

1. Open: **https://github.com/settings/ssh/new**
2. Title: `atlas-cursor-mac` (or any name)
3. Key (paste this entire line):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvClKh43Onx7JB59Y4NL9fIstTuPPz0+vsQ6PvTQNG8 tonyswartz@github
```

4. Click **Add SSH key**.

After that, **Sync** in Cursor (and `git push` in terminal) will use SSH and won't get stuck.

To verify: run `ssh -T git@github.com` — you should see "Hi tonyswartz! You've successfully authenticated..."
