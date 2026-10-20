FROM node:24-slim
WORKDIR /app
# Immutable upstream revision reviewed for image/reference handling.
ADD https://github.com/stufently/gpt-web-gateway.git#893f553be358210a5c045aa9f62b56ba1edc5c78 /app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm ci --omit=dev && npx patchright install --with-deps chrome \
    && chmod -R a+rX /ms-playwright \
    && apt-get update && apt-get install -y --no-install-recommends xvfb xauth tini \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
COPY patch-gateway.cjs /tmp/patch-gateway.cjs
RUN node /tmp/patch-gateway.cjs /app \
    && mkdir -p /app/auth /app/public/images && chown -R node:node /app
USER node
ENV HEADLESS=false PORT=3000 BIND_HOST=0.0.0.0 BROWSER_ENGINE=patchright \
    HUMAN_VERIFICATION_ONLY=1 MAX_CONCURRENT_JOBS=1 MAX_BATCH_N=1 \
    TEXT_STALL_RETRIES=0 DISABLE_CHATGPT_MEMORY=0 STALL_SNAPSHOTS=0 \
    GENERATION_MAX_TIMEOUT_SEC=540
VOLUME ["/app/auth", "/app/public/images"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["xvfb-run", "-a", "--error-file=/dev/stderr", "--server-args=-screen 0 1280x800x24 -ac -nolisten tcp", "node", "src/server.js"]
