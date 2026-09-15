<?php
require_once __DIR__ . '/../src/auth.php';
console_session_start();

$err = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $u = $_POST['user'] ?? '';
    $p = $_POST['pass'] ?? '';
    if (console_check_login($u, $p)) {
        console_do_login();
        header('Location: index.php');
        exit;
    }
    $err = 'Invalid credentials.';
    usleep(400000); // small throttle
}
if (is_logged_in()) { header('Location: index.php'); exit; }
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Console Login</title>
<link rel="stylesheet" href="assets/app.css">
</head>
<body class="login-body">
  <form class="login-card" method="post" autocomplete="off">
    <h1>SAM9X75 Security Console</h1>
    <?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
    <label>User <input name="user" autofocus></label>
    <label>Password <input name="pass" type="password"></label>
    <button type="submit">Sign in</button>
  </form>
</body>
</html>
