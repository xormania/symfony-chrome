<?php

declare(strict_types=1);

// Mago extension host for the fixture workspace. Adapted from mago-serena_v2-poc.
// Two extensions: a bounded after-analysis observer that records selected constructor
// references from Mago's own final graph, and the Byte-Kitsune Symfony wiring extension
// fed from the sanitized compiled-container reference that mate-prepare exports.

use ByteKitsune\MagoSymfonyWiring\SymfonyWiringExtension;
use Mago\Sdk\Analyzer\AfterAnalysisContext;
use Mago\Sdk\Analyzer\AfterAnalysisHook;
use Mago\Sdk\Analyzer\Metadata\MemberIdentifier;
use Mago\Sdk\Analyzer\Plugin;
use Mago\Sdk\Analyzer\PluginDefinition;
use Mago\Sdk\Analyzer\PluginRegistry;
use Mago\Sdk\Extension;
use Mago\Sdk\Worker;

$root = dirname(__DIR__);
require $root . '/vendor/autoload.php';

$observer = new class implements Plugin, AfterAnalysisHook {
    public function getDefinition(): PluginDefinition
    {
        return new PluginDefinition(
            'symfony-chrome/wiring-observer',
            'Compiled wiring graph observer',
            'Records selected constructor references from the final native graph.',
        );
    }

    public function register(PluginRegistry $registry): void
    {
        $registry->registerAfterAnalysisHook($this);
    }

    public function afterAnalysis(AfterAnalysisContext $context): void
    {
        $requested = getenv('DEV_WIRING_SYMBOLS');
        $owners = $requested === false
            ? ['App\\Controller\\ReadyController']
            : json_decode($requested, true, flags: JSON_THROW_ON_ERROR);
        if (!is_array($owners) || $owners === [] || count($owners) > 8) {
            throw new RuntimeException('Expected one to eight selected class names.');
        }
        $edges = static fn(iterable $references): array => array_map(static fn($reference): array => [
            'source' => $reference->source,
            'target' => $reference->target,
            'kind' => $reference->kind->name,
        ], [...$references]);
        $symbols = [];
        foreach ($owners as $selected) {
            if (!is_string($selected) || strlen($selected) > 200) {
                throw new RuntimeException('Invalid selected class name.');
            }
            $declaration = $context->codebase->getClassLike($selected);
            $symbols[$selected] = [
                'owner' => $selected,
                'member' => '__construct',
                'declaration' => $declaration === null ? null : [
                    'name' => $declaration->originalName,
                    'location' => $declaration->location,
                    'parent' => $declaration->directParentClass,
                ],
                'references' => $edges($context->analysis->references->getReferencesFrom(new MemberIdentifier($selected, '__construct'))),
            ];
        }
        $files = [];
        foreach ($context->analysis->files as $file) {
            $files[] = ['path' => $file->file, 'size' => $file->size];
        }
        $path = getenv('DEV_WIRING_OBSERVATION');
        if (!is_string($path) || !str_starts_with($path, '/evidence/')) {
            throw new RuntimeException('DEV_WIRING_OBSERVATION must select a retained /evidence/ file.');
        }
        file_put_contents($path, json_encode([
            'observer' => 'symfony-chrome/wiring-observer',
            'wiring_enabled' => getenv('DEV_WIRING') !== '0',
            'files' => $files,
            'symbols' => $symbols,
        ], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
    }
};

$extensions = [new Extension('symfony-chrome/observer', 'Wiring observation', '1.0.0', analyzerPlugins: [$observer])];
if (getenv('DEV_WIRING') !== '0') {
    $extensions[] = SymfonyWiringExtension::fromContainerReference($root, '.mago/container-reference.dev.json');
}
(new Worker(...$extensions))->run();
