<?php

declare(strict_types=1);

namespace App\Controller;

use App\Ci\BindingProbe;
use Symfony\Component\DependencyInjection\Attribute\Autowire;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpKernel\Profiler\Profiler;
use Symfony\Component\HttpKernel\Attribute\AsController;
use Symfony\Component\Routing\Attribute\Route;

/** Test-only controller copied into disposable integration applications. */
#[AsController]
final class ContractController
{
    public function __construct(#[Autowire(service: 'profiler')] private readonly Profiler $profiler, private readonly BindingProbe $probe) {}

    #[Route('/_ci/observe', methods: ['GET'])]
    public function observe(Request $request): JsonResponse
    {
        return new JsonResponse(['marker' => $this->probe->send((string) $request->query->get('marker', ''))]);
    }

    #[Route('/_ci/redirect', methods: ['GET'])]
    public function redirect(Request $request): RedirectResponse
    {
        return new RedirectResponse('/_ci/observe?marker=' . rawurlencode((string) $request->query->get('marker', '')));
    }

    #[Route('/_ci/profile/{token}', requirements: ['token' => '[0-9a-f]{6}'], methods: ['GET'])]
    public function profile(string $token): JsonResponse
    {
        $profile = $this->profiler->loadProfile($token);
        if ($profile === null || $profile === false) {
            return new JsonResponse(['available' => false, 'token' => $token], 404);
        }
        return new JsonResponse(['available' => true, 'token' => $profile->getToken(), 'url' => $profile->getUrl(),
            'method' => $profile->getMethod(), 'status' => $profile->getStatusCode()]);
    }

    #[Route('/_ci/browser', methods: ['GET'])]
    public function browser(): Response
    {
        return new Response('<!doctype html><html><head><title>Browser contract</title><link rel="icon" href="/_ci/icon.svg"></head><body><h1>Symfony Chrome contract</h1><button id="local">Local action</button><output id="count">0</output><script src="/_ci/script.js"></script></body></html>', 200,
            ['Content-Security-Policy' => "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'"]);
    }

    #[Route('/_ci/icon.svg', methods: ['GET'])]
    public function icon(): Response
    {
        return new Response('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>', 200, ['Content-Type' => 'image/svg+xml']);
    }

    #[Route('/_ci/script.js', methods: ['GET'])]
    public function script(): Response
    {
        return new Response("document.getElementById('local').addEventListener('click', () => { document.getElementById('count').textContent = String(Number(document.getElementById('count').textContent) + 1); });", 200,
            ['Content-Type' => 'text/javascript']);
    }

    #[Route('/_ci/fault', methods: ['GET'])]
    public function fault(): Response
    {
        return new Response('Deliberate contract fault', 503);
    }
}
