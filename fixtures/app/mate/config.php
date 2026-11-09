<?php

declare(strict_types=1);

use Symfony\Component\DependencyInjection\Loader\Configurator\ContainerConfigurator;

// AI Mate 0.15 context configuration, adapted from mago-serena_v2-poc. The inspection-dev
// context reads this application's dev cache, profiler storage and logs; no fallback to
// the test or prod containers while inspecting a dev run.
return static function (ContainerConfigurator $container): void {
    $container->parameters()
        ->set('mate.php_version', '8.4')
        ->set('ai_mate_symfony.cache_dir', ['inspection-dev' => '%mate.root_dir%/var/cache/dev'])
        ->set('ai_mate_symfony.profiler_dir', ['inspection-dev' => '%mate.root_dir%/var/cache/dev/profiler'])
        ->set('ai_mate_monolog.log_dir', ['inspection-dev' => '%mate.root_dir%/var/log'])
    ;
};
