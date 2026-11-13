#!/usr/bin/env node
'use strict';

let localtunnel;
try {
  localtunnel = require('localtunnel');
} catch (e1) {
  try {
    localtunnel = require('/usr/local/lib/node_modules/localtunnel');
  } catch (e2) {
    try {
      localtunnel = require('./node_modules/localtunnel');
    } catch (e3) {
      console.error('[localtunnel] LỖI: Không tìm thấy gói npm localtunnel. Đang thoát...');
      process.exit(1);
    }
  }
}

const SUBDOMAIN = process.env.LOCALTUNNEL_SUBDOMAIN || 'electrohub';
const STRICT_SUBDOMAIN = process.env.LOCALTUNNEL_STRICT === 'true';
const PORT = parseInt(process.env.PORT || '8000', 10);
const LOCAL_HOST = process.env.LOCAL_HOST || 'app';
const EXPECTED_URL = `https://${SUBDOMAIN}.loca.lt`;
const PING_INTERVAL_MS = 8000;   // 8s heartbeat chống idle timeout từ Cloudflare/loca.lt
const PING_TIMEOUT_MS = 12000;   // 12s timeout tránh false-positive abort khi mạng quốc tế trễ
const MAX_CONSECUTIVE_ERRORS = 5; // Cho phép thử lại 5 lần thay vì vội vàng ngắt tunnel

let currentTunnel = null;
let activeTunnelUrl = null;
let isShuttingDown = false;
let isTunnelConnected = false;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 1. Chờ ứng dụng FastAPI nội bộ sẵn sàng
async function waitForLocalApp() {
  console.log(`[localtunnel] Đang kiểm tra ứng dụng nội bộ http://${LOCAL_HOST}:${PORT}/api/v1/health...`);
  while (!isShuttingDown) {
    try {
      const res = await fetch(`http://${LOCAL_HOST}:${PORT}/api/v1/health`, {
        signal: AbortSignal.timeout(3000)
      });
      if (res.status === 200) {
        console.log('[localtunnel] Ứng dụng nội bộ đã sẵn sàng!');
        return true;
      }
    } catch (_) {}
    console.log('[localtunnel] Ứng dụng nội bộ chưa phản hồi, chờ 1 giây...');
    await sleep(1000);
  }
  return false;
}

// 2. Mở tunnel và giữ đúng subdomain
async function connectTunnel() {
  let attempt = 0;

  while (!isShuttingDown) {
    attempt++;
    let tunnel = null;

    try {
      const opts = {
        port: PORT,
        local_host: LOCAL_HOST,
        subdomain: SUBDOMAIN
      };
      if (process.env.LOCALTUNNEL_HOST) {
        opts.host = process.env.LOCALTUNNEL_HOST;
      }
      tunnel = await localtunnel(opts);
    } catch (err) {
      console.log(`[localtunnel] Lỗi khởi tạo: ${err.message}. Đang thử lại sau 2 giây...`);
      await sleep(2000);
      continue;
    }

    if (!tunnel || !tunnel.url) {
      console.log('[localtunnel] Không nhận được URL từ máy chủ tunnel. Thử lại sau 2s...');
      await sleep(2000);
      continue;
    }

    // Chỉ chấp nhận đúng subdomain đã cấu hình, không dùng domain tạm.
    if (tunnel.url !== EXPECTED_URL) {
      try {
        tunnel.removeAllListeners();
        tunnel.close();
      } catch (_) {}
      console.log(`[localtunnel] Subdomain "${SUBDOMAIN}" đang bận (nhận tạm: ${tunnel.url}). Đang chờ giải phóng để giữ đúng domain ${EXPECTED_URL}... (lần ${attempt}, thử lại sau 4s)`);
      await sleep(4000);
      continue;
    }

    console.log(`[localtunnel] -> Đã xác nhận subdomain chính thức: ${tunnel.url}`);

    activeTunnelUrl = tunnel.url;
    isTunnelConnected = true;

    tunnel.on('error', (err) => {
      console.error(`[localtunnel] Socket warning: ${err.message}`);
      // Một số lỗi socket cho thấy upstream/proxy hỏng nhưng không phát sự kiện close kịp thời.
      if (!isShuttingDown && /connection|socket|closed|reset|refused/i.test(err.message || '')) {
        isTunnelConnected = false;
      }
    });

    tunnel.once('close', () => {
      isTunnelConnected = false;
      if (!isShuttingDown) {
        console.log('[localtunnel] Kết nối socket tunnel đã đóng từ phía máy chủ.');
      }
    });

    console.log(`[localtunnel] -> Đã tạo tunnel: ${activeTunnelUrl}`);

    // Chờ đường truyền public thực sự sẵn sàng (tránh bàn giao tunnel đang trả 502/503).
    let healthy = false;
    for (let probe = 1; probe <= 12; probe++) {
      if (isShuttingDown || !isTunnelConnected) break;
      try {
        const res = await fetch(`${activeTunnelUrl}/api/v1/health`, {
          headers: {
            'bypass-tunnel-reminder': 'true',
            'User-Agent': 'Mozilla/5.0 (compatible; ElectroHubTunnel/1.0)',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
          },
          signal: AbortSignal.timeout(8000)
        });
        if (res.status === 200) {
          healthy = true;
          console.log(`[localtunnel] -> Tunnel sẵn sàng phục vụ: ${activeTunnelUrl} (HTTP 200)`);
          break;
        }
        console.log(`[localtunnel] Chờ tunnel sẵn sàng (${probe}/12, HTTP ${res.status})...`);
      } catch (err) {
        console.log(`[localtunnel] Chờ tunnel sẵn sàng (${probe}/12, ${err.message})...`);
      }
      await sleep(2000);
    }

    if (!healthy) {
      console.log('[localtunnel] Tunnel chưa sẵn sàng sau khi khởi tạo, sẽ tạo lại...');
      try {
        tunnel.removeAllListeners();
        tunnel.close();
      } catch (_) {}
      isTunnelConnected = false;
      await sleep(2000);
      continue;
    }

    return tunnel;
  }
  return null;
}

// 3. Vòng lặp giám sát: phát hiện app rebuild/upstream stale và tự phục hồi khi tunnel public chết (503/502).
async function startMonitor(tunnel) {
  let lastAppHealthy = true;
  let consecutiveErrors = 0;
  while (!isShuttingDown && isTunnelConnected) {
    await sleep(PING_INTERVAL_MS);
    if (isShuttingDown || !isTunnelConnected) break;

    // Kiểm tra app nội bộ để phát hiện app restart/rebuild (container đổi IP/upstream stale).
    let appHealthy = false;
    try {
      const appRes = await fetch(`http://${LOCAL_HOST}:${PORT}/api/v1/health`, {
        signal: AbortSignal.timeout(3000)
      });
      appHealthy = appRes.status === 200;
    } catch (_) {}

    if (!appHealthy) {
      if (lastAppHealthy) {
        console.log(`[localtunnel] Ứng dụng nội bộ (${LOCAL_HOST}:${PORT}) tạm thời bận hoặc chưa phản hồi.`);
      }
      lastAppHealthy = false;
      consecutiveErrors = 0;
      continue;
    }

    if (!lastAppHealthy) {
      // App vừa phục hồi sau khi down/rebuild: kết nối upstream cũ của localtunnel có thể đã stale -> tái tạo.
      console.log(`[localtunnel] Ứng dụng nội bộ đã phục hồi sau gián đoạn. Đang tái khởi tạo tunnel để làm mới upstream...`);
      try {
        tunnel.removeAllListeners();
        tunnel.close();
      } catch (_) {}
      isTunnelConnected = false;
      return;
    }
    lastAppHealthy = true;

    // Kiểm tra đường truyền public. Chỉ tái tạo khi lỗi kéo dài liên tiếp (tránh nhiễu nhất thời).
    const targetUrl = activeTunnelUrl || tunnel.url;
    try {
      const res = await fetch(`${targetUrl}/api/v1/health`, {
        headers: {
          'bypass-tunnel-reminder': 'true',
          'User-Agent': 'Mozilla/5.0 (compatible; ElectroHubTunnel/1.0)',
          'Connection': 'keep-alive',
          'Cache-Control': 'no-cache'
        },
        signal: AbortSignal.timeout(PING_TIMEOUT_MS)
      });
      if (res.status === 200) {
        consecutiveErrors = 0;
      } else {
        consecutiveErrors++;
        console.log(`[localtunnel] Giám sát phản hồi HTTP ${res.status} (lỗi: ${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS})`);
      }
    } catch (err) {
      consecutiveErrors++;
      console.log(`[localtunnel] Gián đoạn đường truyền ngoại vi: ${err.message} (lỗi: ${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS})`);
    }

    if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
      console.log(`[localtunnel] Phát hiện lỗi liên tiếp ${MAX_CONSECUTIVE_ERRORS} lần. Đang tái khởi tạo tunnel...`);
      try {
        tunnel.removeAllListeners();
        tunnel.close();
      } catch (_) {}
      isTunnelConnected = false;
      return;
    }
  }
}

// 4. Giải phóng subdomain sạch sẽ khi nhận SIGTERM / SIGINT từ Docker
async function handleShutdown(signal) {
  if (isShuttingDown) return;
  isShuttingDown = true;
  console.log(`\n[localtunnel] Nhận tín hiệu ${signal}. Đang đóng tunnel...`);

  if (currentTunnel) {
    try {
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 2000);
        currentTunnel.once('close', () => {
          clearTimeout(timer);
          resolve();
        });
        try {
          currentTunnel.close();
        } catch (_) {
          resolve();
        }
      });
      console.log(`[localtunnel] Đã đóng tunnel sạch sẽ.`);
    } catch (err) {
      console.error(`[localtunnel] Lỗi khi giải phóng: ${err.message}`);
    }
    currentTunnel = null;
  }
  process.exit(0);
}

process.on('SIGTERM', () => handleShutdown('SIGTERM'));
process.on('SIGINT', () => handleShutdown('SIGINT'));

// 5. Hàm chạy chính
async function main() {
  const ready = await waitForLocalApp();
  if (!ready) return;

  while (!isShuttingDown) {
    currentTunnel = await connectTunnel();
    if (!currentTunnel || isShuttingDown) break;

    await startMonitor(currentTunnel);
    currentTunnel = null;

    if (!isShuttingDown) {
      console.log('[localtunnel] Phiên tunnel trước đã kết thúc. Đang khởi tạo phiên mới sau 2 giây...');
      await sleep(2000);
    }
  }
}

main().catch((err) => {
  console.error('[localtunnel] Lỗi nghiêm trọng:', err);
  process.exit(1);
});
