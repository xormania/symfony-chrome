<?php

declare(strict_types=1);

namespace App\Ci;

final class LoopbackTransport implements ContractTransport
{
    public function send(string $value): string
    {
        return $value;
    }
}
