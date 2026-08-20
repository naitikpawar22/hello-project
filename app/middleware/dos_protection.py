import logging
import os
import time
from collections import defaultdict
from threading import Lock
from flask import Flask, jsonify, request

logger = logging.getLogger("examforge.dos_protection")


class DoSProtection:
    """
    Thread-safe, sliding-window rate limiter & DoS/DDoS prevention middleware.
    Protects ExamForge against HTTP request floods, auth brute-force attacks,
    file upload memory exhaustion, and abusive client scraping.
    """

    def __init__(self, app=None):
        self.lock = Lock()

        # IP -> list of timestamps (float)
        self.requests = defaultdict(list)

        # IP -> timestamp of ban expiration (float)
        self.banned_ips = {}

        # IP -> count of rate limit violations
        self.violation_counts = defaultdict(int)

        # Config defaults (overridable via env / app.config)
        self.enabled = True
        self.global_rate_limit = 120  # requests per minute per IP
        self.window_seconds = 60      # 1-minute sliding window
        self.ban_duration_seconds = 900  # 15-minute temporary ban on persistent abuse
        self.max_violations_before_ban = 5  # ban after 5 rate limit violations

        # Route-Specific Rate Limits (limit_count, window_seconds)
        self.route_limits = {
            "/api/auth/login": (10, 60),               # Auth brute-force prevention
            "/api/question-banks/import": (10, 60),    # Heavy file upload parsing protection
            "/api/attempts/submit": (15, 60),          # Exam submission flood protection
            "/api/invitations/bulk-send": (10, 60),    # Bulk email spam protection
        }

        # IP Allowlist (e.g. localhost, trusted local networks)
        allowlist_str = os.getenv("EXAMFORGE_DOS_IP_ALLOWLIST", "127.0.0.1,::1")
        self.allowlist = {ip.strip() for ip in allowlist_str.split(",") if ip.strip()}

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        self.enabled = app.config.get("DOS_PROTECTION_ENABLED", True)
        self.global_rate_limit = app.config.get("DOS_GLOBAL_LIMIT_PER_MIN", 120)
        self.ban_duration_seconds = app.config.get("DOS_BAN_DURATION_SEC", 900)

        # Enforce Flask MAX_CONTENT_LENGTH if upload max bytes configured
        max_bytes = app.config.get("MAX_UPLOAD_BYTES")
        if max_bytes:
            app.config["MAX_CONTENT_LENGTH"] = max_bytes

        # Register Flask lifecycle hooks
        app.before_request(self._check_request)
        app.after_request(self._add_security_headers)

        @app.errorhandler(413)
        def request_entity_too_large(error):
            return jsonify(
                error="Payload Too Large",
                message="Request body exceeds maximum allowed size limit.",
                max_bytes=app.config.get("MAX_CONTENT_LENGTH")
            ), 413

        app.extensions["dos_protection"] = self
        logger.info("ExamForge DoS Protection & Rate Limiter initialized successfully.")

    def get_client_ip(self):
        """Extract true client IP address, supporting X-Forwarded-For proxies."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # First IP in chain is client IP
            return forwarded_for.split(",")[0].strip()
        return request.remote_addr or "127.0.0.1"

    def _cleanup_old_records(self, now):
        """Purge expired timestamps and expired bans to prevent memory leaks."""
        cutoff = now - self.window_seconds

        # Clean request timestamps
        for ip in list(self.requests.keys()):
            self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]
            if not self.requests[ip]:
                del self.requests[ip]

        # Clean expired bans
        for ip in list(self.banned_ips.keys()):
            if now > self.banned_ips[ip]:
                del self.banned_ips[ip]
                if ip in self.violation_counts:
                    del self.violation_counts[ip]

    def _check_request(self):
        if not self.enabled:
            return None

        # Exclude static assets (CSS, JS, images) from strict request rate limits
        if request.endpoint == "static":
            return None

        client_ip = self.get_client_ip()

        # Check IP Allowlist
        if client_ip in self.allowlist:
            return None

        now = time.time()

        with self.lock:
            self._cleanup_old_records(now)

            # 1. Check if IP is currently jailed/banned
            if client_ip in self.banned_ips:
                ban_remaining = int(self.banned_ips[client_ip] - now)
                if ban_remaining > 0:
                    logger.warning("Blocked request from jailed IP: %s (remaining: %ds)", client_ip, ban_remaining)
                    resp = jsonify(
                        error="Too Many Requests",
                        message="Your IP address has been temporarily banned due to excessive request traffic.",
                        retry_after=ban_remaining
                    )
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(ban_remaining)
                    return resp

            # 2. Check Route-Specific or Global Rate Limit
            path = request.path
            limit, window = self.route_limits.get(path, (self.global_rate_limit, self.window_seconds))

            recent_requests = [t for t in self.requests[client_ip] if t > (now - window)]

            if len(recent_requests) >= limit:
                self.violation_counts[client_ip] += 1
                violations = self.violation_counts[client_ip]

                # Auto-jail IP if persistent violations occur
                if violations >= self.max_violations_before_ban:
                    self.banned_ips[client_ip] = now + self.ban_duration_seconds
                    logger.error("IP %s auto-jailed for %d seconds after %d DoS violations",
                                 client_ip, self.ban_duration_seconds, violations)
                    resp = jsonify(
                        error="IP Banned",
                        message="Your IP address has been temporarily jailed for security violations.",
                        retry_after=self.ban_duration_seconds
                    )
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(self.ban_duration_seconds)
                    return resp

                retry_after = int(window - (now - recent_requests[0])) if recent_requests else window
                retry_after = max(1, retry_after)
                logger.warning("Rate limit exceeded for IP %s on route %s (%d/%d)",
                               client_ip, path, len(recent_requests), limit)

                resp = jsonify(
                    error="Too Many Requests",
                    message=f"Rate limit exceeded for path {path}. Maximum {limit} requests per {window}s allowed.",
                    retry_after=retry_after
                )
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp

            # Log this request
            self.requests[client_ip].append(now)

        return None

    def _add_security_headers(self, response):
        """Append anti-DoS and browser security headers to all HTTP responses."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Prevent caching sensitive API responses
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        return response

    def unban_ip(self, ip: str) -> bool:
        """Manually unban an IP address."""
        with self.lock:
            if ip in self.banned_ips:
                del self.banned_ips[ip]
                if ip in self.violation_counts:
                    del self.violation_counts[ip]
                return True
        return False

    def get_stats(self):
        """Return real-time monitoring stats for admin security dashboard."""
        now = time.time()
        with self.lock:
            active_ips = len(self.requests)
            active_bans = {ip: int(exp - now) for ip, exp in self.banned_ips.items() if exp > now}
            total_violations = dict(self.violation_counts)

        return {
            "dos_protection_enabled": self.enabled,
            "global_rate_limit_per_min": self.global_rate_limit,
            "active_tracked_ips": active_ips,
            "active_banned_ips": active_bans,
            "total_violations_recorded": total_violations,
        }
