<?php

declare(strict_types=1);

namespace App\Ci;

interface ContractTransport
{
    public function send(string $value): string;
}
