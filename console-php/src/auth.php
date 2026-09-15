<?php
/**
 * SAM9X75-RDK PC Console — session auth.
 * Mirrors the shape of the PIC64 login site (cookie session + require_login),
 * but for the PC console. LAN-only appliance; single shared account.
 */
require_once __DIR__ . '/config.php';

function console_session_start(): void {
    if (session_status() === PHP_SESSION_ACTIVE) return;
    session_name(SESSION_NAME);
    session_set_cookie_params([
        'lifetime' => 0,
        'path'     => '/',
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_start();
}

function is_logged_in(): bool {
    console_session_start();
    return !empty($_SESSION['auth']);
}

/** Validate credentials (constant-time). */
function console_check_login(string $user, string $pass): bool {
    $okUser = hash_equals(CONSOLE_USER, $user);
    $okPass = hash_equals(CONSOLE_PASS, $pass);
    return $okUser && $okPass;
}

function console_do_login(): void {
    console_session_start();
    session_regenerate_id(true);
    $_SESSION['auth'] = true;
    $_SESSION['user'] = CONSOLE_USER;
    $_SESSION['ts']   = time();
}

function console_logout(): void {
    console_session_start();
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $p = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'] ?? '', $p['secure'] ?? false, $p['httponly'] ?? true);
    }
    session_destroy();
}

/** Redirect browsers to the login page; 401 JSON for API/XHR callers. */
function require_login(bool $json = false): void {
    if (is_logged_in()) return;
    if ($json) {
        http_response_code(401);
        header('Content-Type: application/json');
        echo json_encode(['ok' => false, 'error' => 'not_authenticated']);
        exit;
    }
    header('Location: login.php');
    exit;
}
