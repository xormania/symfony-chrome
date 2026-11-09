<?php

declare(strict_types=1);

// A real public/lab directory prevents PHP's implicit index fallback for /lab/*.
// Preserve static assets while explicitly handing all application routes to Symfony.
$public = realpath($_SERVER['DOCUMENT_ROOT']);
if (false === $public) {
    throw new RuntimeException('Consumer document root does not exist');
}
$path = rawurldecode(parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?? '/');
$file = realpath($public.$path);
if (false !== $file && str_starts_with($file, $public.DIRECTORY_SEPARATOR) && is_file($file)) {
    return false;
}
$_SERVER['SCRIPT_NAME'] = '/index.php';
$_SERVER['SCRIPT_FILENAME'] = $public.'/index.php';
require $public.'/index.php';
