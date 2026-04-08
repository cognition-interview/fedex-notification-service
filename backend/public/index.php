<?php

declare(strict_types=1);

require_once __DIR__ . '/../vendor/autoload.php';

use DI\Container;
use FedEx\Controllers\BusinessController;
use FedEx\Controllers\InsightsController;
use FedEx\Controllers\NotificationController;
use FedEx\Controllers\OrderController;
use Slim\Factory\AppFactory;
use Dotenv\Dotenv;

// Load .env
$dotenv = Dotenv::createImmutable(dirname(__DIR__, 2));
$dotenv->load();

$app = AppFactory::create();
$app->addRoutingMiddleware();
$app->addErrorMiddleware(true, true, true);

// CORS
$app->add(function ($request, $handler) {
    if ($request->getMethod() === 'OPTIONS') {
        $response = new \Slim\Psr7\Response();
        return $response
            ->withHeader('Access-Control-Allow-Origin', '*')
            ->withHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization')
            ->withHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
            ->withStatus(200);
    }
    $response = $handler->handle($request);
    return $response
        ->withHeader('Access-Control-Allow-Origin', '*')
        ->withHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization')
        ->withHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS');
});

// ── Orders ────────────────────────────────────────────────────────────────────
$app->get('/api/orders/stats',       [OrderController::class, 'getOrderStats']);
$app->get('/api/orders',             [OrderController::class, 'getOrders']);
$app->get('/api/orders/{id}',        [OrderController::class, 'getOrderById']);

// ── Businesses ────────────────────────────────────────────────────────────────
$app->get('/api/businesses',         [BusinessController::class, 'getBusinesses']);
$app->get('/api/businesses/{id}',    [BusinessController::class, 'getBusinessById']);

// ── Notifications ─────────────────────────────────────────────────────────────
$app->patch('/api/notifications/read-all', [NotificationController::class, 'markAllRead']);
$app->get('/api/notifications',            [NotificationController::class, 'getNotifications']);
$app->patch('/api/notifications/{id}/read', [NotificationController::class, 'markOneRead']);

// ── Insights ──────────────────────────────────────────────────────────────────
$app->get('/api/insights', [InsightsController::class, 'getInsights']);

// Preflight
$app->options('/{routes:.+}', function ($request, $response) {
    return $response;
});

$app->run();
