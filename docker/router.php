<?php
// PHP built-in server router for the fixture app: static files from public/, everything else to the front controller.
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?? '/';
if ('/' !== $path && is_file('/workspace/public'.$path)) {
    return false;
}
$_SERVER['SCRIPT_NAME'] = '/index.php';
$_SERVER['SCRIPT_FILENAME'] = '/workspace/public/index.php';
require '/workspace/public/index.php';
