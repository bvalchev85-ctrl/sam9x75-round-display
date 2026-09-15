<?php
require_once __DIR__ . '/../src/auth.php';
console_logout();
header('Location: login.php');
exit;
