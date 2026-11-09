<?php

declare(strict_types=1);

namespace App\Ci;

final class BindingProbe
{
    public function __construct(private readonly ContractTransport $transport) {}

    public function send(string $value): string
    {
        return $this->transport->send($value);
    }
}
