<?php

declare(strict_types=1);

namespace Xormania\ChromeBundle;

use Symfony\Component\HttpKernel\Bundle\AbstractBundle;

/**
 * Runtime bundle. Installable in production; carries no Profiler, Mate, or Chrome DevTools MCP dependency.
 */
final class ChromeBundle extends AbstractBundle
{
    public function getPath(): string
    {
        return \dirname(__DIR__);
    }
}
