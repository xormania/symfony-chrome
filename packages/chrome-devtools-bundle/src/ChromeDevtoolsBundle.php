<?php

declare(strict_types=1);

namespace Xormania\ChromeDevtoolsBundle;

use Symfony\Component\HttpKernel\Bundle\AbstractBundle;

/**
 * Development bundle. Belongs in require-dev; a production install must boot without it.
 */
final class ChromeDevtoolsBundle extends AbstractBundle
{
    public function getPath(): string
    {
        return \dirname(__DIR__);
    }
}
