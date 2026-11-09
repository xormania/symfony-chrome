<?php

declare(strict_types=1);

namespace App\Controller;

use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

/**
 * Readiness probe used by the development environment's health check.
 * Reports which optional bundles are present so prod-mode runs are distinguishable.
 */
final class ReadyController
{
    #[Route('/_dev/ready', name: 'dev_ready', methods: ['GET'])]
    public function __invoke(): JsonResponse
    {
        return new JsonResponse([
            'ready' => true,
            'chrome_bundle' => class_exists(\Xormania\ChromeBundle\ChromeBundle::class),
            'chrome_devtools_bundle' => class_exists(\Xormania\ChromeDevtoolsBundle\ChromeDevtoolsBundle::class),
            'profiler' => class_exists(\Symfony\Bundle\WebProfilerBundle\WebProfilerBundle::class),
        ]);
    }
}
