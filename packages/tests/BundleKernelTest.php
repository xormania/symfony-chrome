<?php

declare(strict_types=1);

use App\Kernel;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

final class BundleKernelTest extends TestCase
{
    public function testBundlesAreRegisteredAndRealRequestIsHandled(): void
    {
        $kernel = new Kernel('test', false);
        try {
            $kernel->boot();
            self::assertArrayHasKey('ChromeBundle', $kernel->getBundles());
            self::assertArrayHasKey('ChromeDevtoolsBundle', $kernel->getBundles());
            self::assertArrayHasKey('WebProfilerBundle', $kernel->getBundles());
            $response = $kernel->handle(Request::create('/_dev/ready'));
            self::assertSame(200, $response->getStatusCode());
            self::assertTrue(json_decode($response->getContent(), true, flags: JSON_THROW_ON_ERROR)['ready']);
            $kernel->terminate(Request::create('/_dev/ready'), $response);
        } finally {
            $kernel->shutdown();
        }
    }
}
