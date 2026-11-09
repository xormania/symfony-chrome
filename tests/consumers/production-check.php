<?php

declare(strict_types=1);

use App\Kernel;
use Composer\InstalledVersions;
use Symfony\Component\HttpFoundation\Request;

require getcwd() . '/vendor/autoload.php';
$environment = getenv('APP_ENV') ?: 'prod';
$kernel = new Kernel($environment, false);
$assertions = 0;
$check = static function (bool $condition, string $message) use (&$assertions): void {
    ++$assertions;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};
try {
    $kernel->boot();
    $bundles = $kernel->getBundles();
    $check(isset($bundles['ChromeBundle']), 'Runtime bundle is not registered');
    $check($kernel->getEnvironment() === $environment && !$kernel->isDebug(), 'Wrong kernel mode');
    if ($environment === 'prod') {
        foreach (['xormania/chrome-devtools-bundle', 'symfony/web-profiler-bundle', 'symfony/ai-mate', 'carthage-software/mago', 'byte-kitsune/mago-symfony-wiring'] as $package) {
            $check(!InstalledVersions::isInstalled($package), 'Development dependency installed: ' . $package);
        }
        $check(!isset($bundles['ChromeDevtoolsBundle']) && !isset($bundles['WebProfilerBundle']), 'Development bundle registered');
        $check(!$kernel->getContainer()->has('profiler'), 'Profiler service is enabled');
        $router = $kernel->getContainer()->get('router');
        foreach ($router->getRouteCollection() as $name => $route) {
            $check(!str_starts_with($name, '_profiler') && !str_starts_with($name, '_wdt'), 'Profiler route is exposed');
        }
    } else {
        $check(isset($bundles['ChromeDevtoolsBundle']), 'Development consumer bundle is not registered');
    }
    $request = Request::create('/_ci/ready');
    $response = $kernel->handle($request);
    $check($response->getStatusCode() === 200, 'Consumer route failed');
    $check(json_decode($response->getContent(), true, flags: JSON_THROW_ON_ERROR)['ready'] === true, 'Consumer response is invalid');
    $kernel->terminate($request, $response);
    echo json_encode(['assertions' => $assertions, 'environment' => $environment, 'bundles' => array_keys($bundles)], JSON_THROW_ON_ERROR) . "\n";
} finally {
    $kernel->shutdown();
}
