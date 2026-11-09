<?php

use App\Kernel;
use Symfony\Component\HttpFoundation\Request;

require dirname(__DIR__) . '/vendor/autoload.php';

$environment = $_SERVER['APP_ENV'] ?? getenv('APP_ENV') ?: 'dev';
$debug = filter_var($_SERVER['APP_DEBUG'] ?? (getenv('APP_DEBUG') !== false ? getenv('APP_DEBUG') : ($environment === 'prod' ? '0' : '1')), FILTER_VALIDATE_BOOL);
$kernel = new Kernel($environment, $debug);
$request = Request::createFromGlobals();
$response = $kernel->handle($request);
$response->send();
$kernel->terminate($request, $response);
