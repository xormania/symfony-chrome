<?php
$loader = require $argv[2];
$app = $argv[1];
foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator($app . '/src')) as $file) {
    if ($file->getExtension() !== 'php') continue;
    $relative = substr($file->getPathname(), strlen($app . '/src/'), -4);
    $loader->addClassMap(['App\\' . str_replace('/', '\\', $relative) => $file->getPathname()]);
}
$loader->setClassMapAuthoritative(false);
$_SERVER['APP_ENV'] = $_ENV['APP_ENV'] = 'dev';
$_SERVER['APP_DEBUG'] = $_ENV['APP_DEBUG'] = '1';
$kernel = new App\Kernel('dev', true);
$kernel->boot();
$request = Symfony\Component\HttpFoundation\Request::create('/_ci/observe?marker=native-profiler-wiring');
$response = $kernel->handle($request);
$kernel->terminate($request, $response);
if ($response->getStatusCode() !== 200 || json_decode($response->getContent(), true)['marker'] !== 'native-profiler-wiring') throw new RuntimeException('Exact fixture controller did not respond');
echo json_encode(['status' => $response->getStatusCode(), 'marker' => json_decode($response->getContent(), true)['marker'], 'profiler_token' => $response->headers->get('X-Debug-Token'), 'symfony' => Symfony\Component\HttpKernel\Kernel::VERSION]), PHP_EOL;
