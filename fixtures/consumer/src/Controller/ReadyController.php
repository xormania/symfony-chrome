<?php

declare(strict_types=1);
namespace App\Controller;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\HttpKernel\KernelInterface;
final class ReadyController
{
    #[Route('/_ci/ready', methods: ['GET'])]
    public function __invoke(KernelInterface $kernel): JsonResponse
    {
        return new JsonResponse(['ready' => true, 'environment' => $kernel->getEnvironment(), 'bundles' => array_keys($kernel->getBundles())]);
    }
}
