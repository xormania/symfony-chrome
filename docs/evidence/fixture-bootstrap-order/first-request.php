<?php
// Use the locked installed dependency tree while mapping App classes to this
// owned disposable app; no vendor files are changed.
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
$request = Symfony\Component\HttpFoundation\Request::create('/_ci/browser');
$response = $kernel->handle($request);
$kernel->terminate($request, $response);
if ($response->getStatusCode() !== 200
    || !str_contains($response->getContent(), 'Symfony Chrome contract')
    || !str_contains($response->getContent(), 'Local action')) {
    throw new RuntimeException('First native request did not resolve the final fixture route');
}
echo json_encode(['first_request_status' => $response->getStatusCode(),
    'known_heading' => true, 'known_button' => true,
    'profiler_token' => $response->headers->get('X-Debug-Token'),
    'symfony' => Symfony\Component\HttpKernel\Kernel::VERSION]), PHP_EOL;
