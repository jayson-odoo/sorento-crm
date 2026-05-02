# Attachment fixtures

Drop sample files here for the multipart upload scenario:

- `small.pdf`   ~ 50 KB
- `medium.pdf`  ~ 500 KB
- `large.pdf`   ~ 5 MB

Files in this directory are gitignored. Generate locally:

```bash
dd if=/dev/urandom of=small.pdf  bs=1024 count=50
dd if=/dev/urandom of=medium.pdf bs=1024 count=500
dd if=/dev/urandom of=large.pdf  bs=1024 count=5120
```
