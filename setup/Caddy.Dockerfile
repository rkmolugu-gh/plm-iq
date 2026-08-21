# Caddy with the Cloudflare DNS-01 module (needed for the tenant wildcard).
# Versions are pinned for reproducible go-live builds.
FROM caddy:2.9-builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare@v0.1.0

FROM caddy:2.9

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:80/ || exit 1
