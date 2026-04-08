<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Controllers\OrderController;
use FedEx\Database;
use PHPUnit\Framework\TestCase;
use Slim\Psr7\Factory\ServerRequestFactory;
use Slim\Psr7\Response;

class OrderControllerTest extends TestCase
{
    private function mockPdo(): \PDO
    {
        return $this->createMock(\PDO::class);
    }

    private function mockStmt(mixed $fetchResult = null, mixed $fetchAllResult = [], mixed $fetchColumnResult = 0): \PDOStatement
    {
        $stmt = $this->createMock(\PDOStatement::class);
        $stmt->method('bindValue')->willReturn(true);
        $stmt->method('execute')->willReturn(true);
        $stmt->method('fetch')->willReturn($fetchResult);
        $stmt->method('fetchAll')->willReturn($fetchAllResult);
        $stmt->method('fetchColumn')->willReturn($fetchColumnResult);
        $stmt->method('rowCount')->willReturn(1);
        return $stmt;
    }

    private function makeRequest(string $method, string $uri, array $queryParams = [], string $body = ''): \Psr\Http\Message\ServerRequestInterface
    {
        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest($method, $uri);
        if (!empty($queryParams)) {
            $request = $request->withQueryParams($queryParams);
        }
        if ($body !== '') {
            $request->getBody()->write($body);
            $request = $request->withBody($request->getBody());
        }
        return $request;
    }

    protected function tearDown(): void
    {
        // Reset the Database singleton after each test
        $ref = new \ReflectionProperty(Database::class, 'instance');
        $ref->setAccessible(true);
        $ref->setValue(null, null);
    }

    // ── GET /api/orders ───────────────────────────────────────────────────────

    public function testGetOrders(): void
    {
        $orders = [
            ['id' => 'ord-001', 'tracking_number' => '7489001', 'status' => 'In Transit',
             'origin' => 'Memphis, TN', 'destination' => 'New York, NY',
             'business_name' => 'Acme Corp', 'business_id' => 'biz-001'],
            ['id' => 'ord-002', 'tracking_number' => '7489002', 'status' => 'Delivered',
             'origin' => 'Louisville, KY', 'destination' => 'Chicago, IL',
             'business_name' => 'Acme Corp', 'business_id' => 'biz-001'],
        ];

        $listStmt  = $this->mockStmt(null, $orders);
        $countStmt = $this->mockStmt(null, [], 2);

        $pdo = $this->mockPdo();
        $pdo->expects($this->exactly(2))
            ->method('prepare')
            ->willReturnOnConsecutiveCalls($listStmt, $countStmt);

        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['page' => '1', 'limit' => '10']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('orders', $body);
        $this->assertArrayHasKey('total', $body);
        $this->assertCount(2, $body['orders']);
        $this->assertSame(2, $body['total']);
        $this->assertSame(1, $body['page']);
    }

    public function testGetOrdersFilteredByBusinessId(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['businessId' => 'biz-999']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame(0, $body['total']);
    }

    public function testGetOrdersRespectsPagination(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 50);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['page' => '3', 'limit' => '5']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame(3, $body['page']);
        $this->assertSame(5, $body['limit']);
    }

    // ── GET /api/orders/{id} ──────────────────────────────────────────────────

    public function testGetOrderById(): void
    {
        $order = [
            'id' => 'ord-001', 'tracking_number' => '7489001', 'status' => 'In Transit',
            'origin' => 'Memphis, TN', 'destination' => 'New York, NY',
            'business_name' => 'Acme Corp', 'contact_email' => 'test@example.com', 'business_id' => 'biz-001',
        ];
        $events = [
            ['id' => 'evt-001', 'event_type' => 'In Transit', 'location' => 'Memphis, TN',
             'description' => 'Package en route', 'occurred_at' => '2026-04-05T10:00:00Z'],
        ];

        $orderStmt  = $this->mockStmt($order);
        $eventsStmt = $this->mockStmt(null, $events);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($orderStmt, $eventsStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders/ord-001');
        $response   = new Response();

        $result = $controller->getOrderById($request, $response, ['id' => 'ord-001']);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('ord-001', $body['id']);
        $this->assertSame('7489001', $body['tracking_number']);
        $this->assertArrayHasKey('shipment_events', $body);
        $this->assertCount(1, $body['shipment_events']);
    }

    public function testGetOrderByIdReturns404ForMissing(): void
    {
        $orderStmt = $this->mockStmt(false); // fetch returns false = not found

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturn($orderStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders/nonexistent');
        $response   = new Response();

        $result = $controller->getOrderById($request, $response, ['id' => 'nonexistent']);

        $this->assertSame(404, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('error', $body);
    }

    // ── GET /api/orders/stats ─────────────────────────────────────────────────

    public function testGetOrderStats(): void
    {
        $statsRow = [
            'total' => '20', 'picked_up' => '2', 'in_transit' => '8',
            'out_for_delivery' => '3', 'delivered' => '5', 'delayed' => '1', 'exception' => '1',
        ];
        $recentOrders = [
            ['id' => 'ord-001', 'tracking_number' => '7489001', 'status' => 'Delivered',
             'origin' => 'Memphis, TN', 'destination' => 'New York, NY',
             'created_at' => '2026-04-05', 'business_name' => 'Acme'],
        ];

        $statsStmt   = $this->mockStmt($statsRow);
        $recentStmt  = $this->mockStmt(null, $recentOrders);
        $notifStmt   = $this->mockStmt(null, [], 4);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')
            ->willReturnOnConsecutiveCalls($statsStmt, $recentStmt, $notifStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders/stats');
        $response   = new Response();

        $result = $controller->getOrderStats($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('by_status', $body);
        $this->assertArrayHasKey('recent_orders', $body);
        $this->assertArrayHasKey('unread_notifications', $body);
        $this->assertSame(20, $body['by_status']['total']);
        $this->assertSame(4, $body['unread_notifications']);
    }

    // ── PATCH /api/orders/{id}/status (proxied to Function App) ─────────────

    private function makeProxyController(int $httpCode, string $responseBody): OrderController
    {
        // Create a partial mock that overrides proxyToFunctionApp
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyToFunctionApp'])
            ->getMock();

        $controller->method('proxyToFunctionApp')
            ->willReturn(['status' => $httpCode, 'body' => $responseBody]);

        return $controller;
    }

    public function testUpdateOrderStatusMissingFunctionAppUrlReturns503(): void
    {
        $orig = $_ENV['FUNCTION_APP_URL'] ?? null;
        unset($_ENV['FUNCTION_APP_URL']);

        $controller = new OrderController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(503, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('FUNCTION_APP_URL not configured', $body['error']);

        if ($orig !== null) {
            $_ENV['FUNCTION_APP_URL'] = $orig;
        }
    }

    public function testUpdateOrderStatusProxies200Response(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $orderJson = json_encode([
            'id' => 'ord-001', 'tracking_number' => '7489001', 'status' => 'In Transit',
            'shipment_events' => [],
        ]);
        $controller = $this->makeProxyController(200, $orderJson);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit', 'location' => 'Memphis, TN']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('ord-001', $body['id']);
        $this->assertSame('In Transit', $body['status']);
    }

    public function testUpdateOrderStatusProxies422ForInvalidStatus(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $errorJson = json_encode(['error' => 'Invalid status', 'allowed' => ['Picked Up', 'In Transit']]);
        $controller = $this->makeProxyController(422, $errorJson);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'Flying']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(422, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('error', $body);
    }

    public function testUpdateOrderStatusProxies404ForMissingOrder(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $errorJson = json_encode(['error' => 'Order not found']);
        $controller = $this->makeProxyController(404, $errorJson);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ghost/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ghost']);

        $this->assertSame(404, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Order not found', $body['error']);
    }

    public function testUpdateOrderStatusReturns502OnCurlFailure(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyToFunctionApp'])
            ->getMock();

        $controller->method('proxyToFunctionApp')
            ->willReturn([
                'status' => 502,
                'body'   => json_encode(['error' => 'Function App unavailable: Connection refused']),
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(502, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertStringContainsString('Function App unavailable', $body['error']);
    }

    public function testUpdateOrderStatusBuildsCorrectTargetUrl(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyToFunctionApp'])
            ->getMock();

        $controller->expects($this->once())
            ->method('proxyToFunctionApp')
            ->with(
                'https://fedex-update-status.azurewebsites.net/api/orders/ord-123/status',
                $this->anything()
            )
            ->willReturn(['status' => 200, 'body' => '{}']);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-123/status');
        $request->getBody()->write(json_encode(['status' => 'Delivered']));
        $response = new Response();

        $controller->updateOrderStatus($request, $response, ['id' => 'ord-123']);
    }

    public function testUpdateOrderStatusForwardsRequestBody(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net';

        $sentBody = json_encode(['status' => 'Delayed', 'location' => 'Nashville, TN', 'description' => 'Weather delay']);

        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyToFunctionApp'])
            ->getMock();

        $controller->expects($this->once())
            ->method('proxyToFunctionApp')
            ->with($this->anything(), $sentBody)
            ->willReturn(['status' => 200, 'body' => '{}']);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write($sentBody);
        $response = new Response();

        $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);
    }

    public function testUpdateOrderStatusTrimsTrailingSlashFromUrl(): void
    {
        $_ENV['FUNCTION_APP_URL'] = 'https://fedex-update-status.azurewebsites.net/';

        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyToFunctionApp'])
            ->getMock();

        $controller->expects($this->once())
            ->method('proxyToFunctionApp')
            ->with(
                'https://fedex-update-status.azurewebsites.net/api/orders/ord-001/status',
                $this->anything()
            )
            ->willReturn(['status' => 200, 'body' => '{}']);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);
    }

    // ── GET /api/orders — additional filter coverage ─────────────────────────

    public function testGetOrdersFilteredByStatus(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['status' => 'Delivered']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testGetOrdersFilteredByServiceType(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['serviceType' => 'FedEx Express']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testGetOrdersFilteredByServiceTypeSnakeCase(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['service_type' => 'FedEx Ground']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testGetOrdersFilteredByDateRange(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', [
            'fromDate' => '2026-01-01',
            'toDate'   => '2026-04-01',
        ]);
        $response = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testGetOrdersFilteredBySearch(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', ['search' => 'Memphis']);
        $response   = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testGetOrdersWithAllFiltersCombined(): void
    {
        $listStmt  = $this->mockStmt(null, []);
        $countStmt = $this->mockStmt(null, [], 0);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders', [
            'businessId'  => 'biz-001',
            'status'      => 'In Transit',
            'serviceType' => 'FedEx Express',
            'fromDate'    => '2026-01-01',
            'toDate'      => '2026-04-01',
            'search'      => 'TRK',
            'page'        => '2',
            'limit'       => '5',
        ]);
        $response = new Response();

        $result = $controller->getOrders($request, $response);
        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame(2, $body['page']);
        $this->assertSame(5, $body['limit']);
    }

    // ── GET /api/orders/stats — with businessId ──────────────────────────────

    public function testGetOrderStatsFilteredByBusinessId(): void
    {
        $statsRow = [
            'total' => '10', 'picked_up' => '1', 'in_transit' => '3',
            'out_for_delivery' => '2', 'delivered' => '3', 'delayed' => '0', 'exception' => '1',
        ];
        $recentOrders = [];

        $statsStmt  = $this->mockStmt($statsRow);
        $recentStmt = $this->mockStmt(null, $recentOrders);
        $notifStmt  = $this->mockStmt(null, [], 2);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')
            ->willReturnOnConsecutiveCalls($statsStmt, $recentStmt, $notifStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $request    = $this->makeRequest('GET', '/api/orders/stats', ['businessId' => 'biz-001']);
        $response   = new Response();

        $result = $controller->getOrderStats($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame(10, $body['by_status']['total']);
        $this->assertSame(2, $body['unread_notifications']);
    }

}
