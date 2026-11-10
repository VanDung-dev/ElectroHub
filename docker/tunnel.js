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
const PING_INTERVAL_MS = 25000;

let currentTunnel = null;
let activeTunnelUrl = null;
let isShuttingDown = false;

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

// 2. Mở tunnel và áp dụng ngay lập tức
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

    // Nếu máy chủ loca.lt cấp URL khác do phiên cũ đang trong chu kỳ giải phóng (~50s)
    if (tunnel.url !== EXPECTED_URL) {
      if (STRICT_SUBDOMAIN) {
        try {
          tunnel.removeAllListeners();
          tunnel.close();
        } catch (_) {}
        console.log(`[localtunnel] Đang chờ giải phóng subdomain "${SUBDOMAIN}"... (lần thử ${attempt}, tiếp tục sau 4s)`);
        await sleep(4000);
        continue;
      } else {
        // Áp dụng ngay lập tức URL được cấp (0.1 giây), không bắt người dùng chờ đợi!
        console.log(`[localtunnel] Subdomain "${SUBDOMAIN}" đang bận phiên cũ trên máy chủ loca.lt.`);
        console.log(`[localtunnel] -> ÁP DỤNG NGAY LẬP TỨC: ${tunnel.url}`);
      }
    } else {
      console.log(`[localtunnel] -> Đã xác nhận subdomain chính thức: ${tunnel.url}`);
    }

    activeTunnelUrl = tunnel.url;

    tunnel.on('error', (err) => {
      console.error(`[localtunnel] Socket warning: ${err.message}`);
    });

    tunnel.on('close', () => {
      if (!isShuttingDown) {
        console.log('[localtunnel] Kết nối tunnel đã đóng từ phía máy chủ.');
      }
    });

    // Kích hoạt đường truyền
    console.log(`[localtunnel] Đang xác thực thông suốt đường truyền: ${activeTunnelUrl}...`);
    let isAwake = false;
    for (let probe = 1; probe <= 6; probe++) {
      if (isShuttingDown) break;
      try {
        const res = await fetch(`${activeTunnelUrl}/api/v1/health`, {
          headers: { 'bypass-tunnel-reminder': 'true' },
          signal: AbortSignal.timeout(4000)
        });
        if (res.status === 200) {
          isAwake = true;
          console.log(`[localtunnel] -> Tunnel đã TỈNH và HOẠT ĐỘNG: ${activeTunnelUrl} (HTTP 200)`);
          break;
        }
        console.log(`[localtunnel] Đang kích hoạt đường truyền (${probe}/6, HTTP ${res.status})...`);
      } catch (err) {
        console.log(`[localtunnel] Đang kích hoạt đường truyền (${probe}/6, đang chờ router)...`);
      }
      await sleep(1000);
    }

    return tunnel;
  }
  return null;
}

// 3. Vòng lặp giám sát định kỳ & gửi heartbeat chống ngủ/503
async function startMonitor(tunnel) {
  let consecutiveErrors = 0;
  while (!isShuttingDown) {
    await sleep(PING_INTERVAL_MS);
    if (isShuttingDown) break;

    const targetUrl = activeTunnelUrl || tunnel.url;
    try {
      const res = await fetch(`${targetUrl}/api/v1/health`, {
        headers: { 'bypass-tunnel-reminder': 'true' },
        signal: AbortSignal.timeout(6000)
      });
      if (res.status === 200) {
        consecutiveErrors = 0;
      } else {
        consecutiveErrors++;
        console.log(`[localtunnel] Giám sát phản hồi HTTP ${res.status} (lỗi: ${consecutiveErrors}/3)`);
      }
    } catch (err) {
      consecutiveErrors++;
      console.log(`[localtunnel] Giám sát gián đoạn kết nối: ${err.message} (lỗi: ${consecutiveErrors}/3)`);
    }

    if (consecutiveErrors >= 3) {
      console.log('[localtunnel] Phát hiện lỗi 503/đơ kết nối 3 lần liên tiếp. Đang tự phục hồi tunnel...');
      try {
        tunnel.close();
      } catch (_) {}
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
        currentTunnel.close();
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
