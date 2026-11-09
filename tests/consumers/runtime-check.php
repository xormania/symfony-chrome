<?php

declare(strict_types=1);

require getcwd().'/vendor/autoload.php';

$kernel = new App\Kernel('dev', true);
$kernel->boot();
$bundles = $kernel->getBundles();
foreach ([Xormania\ChromeBundle\ChromeBundle::class, Xormania\ChromeDevtoolsBundle\ChromeDevtoolsBundle::class] as $class) {
    if (!array_filter($bundles, static fn ($bundle): bool => $bundle instanceof $class)) {
        throw new RuntimeException('Consumer kernel did not register '.$class);
    }
}
$kernel->shutdown();
echo json_encode(['registered' => ['runtime', 'devtools']], JSON_THROW_ON_ERROR).PHP_EOL;
