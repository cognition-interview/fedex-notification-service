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

    // ── PATCH /api/orders/{id}/status — proxy to Azure Function App ────────

    public function testUpdateOrderStatusReturns503WhenNotConfigured(): void
    {
        // Unset function app env vars
        $origUrl = $_ENV['AZURE_FUNCTION_APP_URL'] ?? '';
        $origKey = $_ENV['AZURE_FUNCTION_APP_KEY'] ?? '';
        $_ENV['AZURE_FUNCTION_APP_URL'] = '';
        $_ENV['AZURE_FUNCTION_APP_KEY'] = '';

        $controller = new OrderController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $_ENV['AZURE_FUNCTION_APP_URL'] = $origUrl;
        $_ENV['AZURE_FUNCTION_APP_KEY'] = $origKey;

        $this->assertSame(503, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Function App not configured', $body['error']);
    }

    public function testUpdateOrderStatusProxiesSuccessfully(): void
    {
        $functionResponse = json_encode([
            'id' => 'ord-002', 'tracking_number' => '7489002', 'status' => 'In Transit',
            'shipment_events' => [],
        ]);

        // Use a partial mock to override proxyHttp()
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->expects($this->once())
            ->method('proxyHttp')
            ->with(
                'PATCH',
                $this->stringContains('/api/orders/ord-002/status?code='),
                $this->callback(function ($body) {
                    $data = json_decode($body, true);
                    return $data['status'] === 'In Transit';
                })
            )
            ->willReturn(['body' => $functionResponse, 'httpCode' => 200, 'error' => '']);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-002/status');
        $request->getBody()->write(json_encode([
            'status'      => 'In Transit',
            'location'    => 'Nashville, TN',
            'description' => 'Package departed hub',
        ]));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-002']);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('ord-002', $body['id']);
        $this->assertSame('In Transit', $body['status']);
    }

    public function testUpdateOrderStatusForwards404FromFunctionApp(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['error' => 'Order not found']),
                'httpCode' => 404,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ghost/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ghost']);

        $this->assertSame(404, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Order not found', $body['error']);
    }

    public function testUpdateOrderStatusForwards422FromFunctionApp(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['error' => 'Invalid status', 'allowed' => ['In Transit', 'Delivered']]),
                'httpCode' => 422,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'Flying']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(422, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Invalid status', $body['error']);
    }

    public function testUpdateOrderStatusReturns502OnCurlError(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => false,
                'httpCode' => 0,
                'error'    => 'Could not resolve host',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(502, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Failed to reach Function App', $body['error']);
    }

    public function testUpdateOrderStatusBuildsCorrectUrl(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->expects($this->once())
            ->method('proxyHttp')
            ->with(
                'PATCH',
                $this->equalTo('https://fedex-update-status.azurewebsites.net/api/orders/ord-005/status?code=test-key-123'),
                $this->anything()
            )
            ->willReturn(['body' => '{}', 'httpCode' => 200, 'error' => '']);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-005/status');
        $request->getBody()->write(json_encode(['status' => 'Delivered']));
        $response = new Response();

        $controller->updateOrderStatus($request, $response, ['id' => 'ord-005']);
    }

    public function testUpdateOrderStatusDeliveredProxy(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['id' => 'ord-003', 'status' => 'Delivered', 'actual_delivery' => '2026-04-08']),
                'httpCode' => 200,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-003/status');
        $request->getBody()->write(json_encode(['status' => 'Delivered', 'location' => 'New York, NY']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-003']);
        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('Delivered', $body['status']);
    }

    public function testUpdateOrderStatusDelayedProxy(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['id' => 'ord-003', 'status' => 'Delayed']),
                'httpCode' => 200,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-003/status');
        $request->getBody()->write(json_encode(['status' => 'Delayed', 'description' => 'Weather delay']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-003']);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testUpdateOrderStatusExceptionProxy(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['id' => 'ord-003', 'status' => 'Exception']),
                'httpCode' => 200,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-003/status');
        $request->getBody()->write(json_encode(['status' => 'Exception', 'description' => 'Address issue']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-003']);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testUpdateOrderStatusOutForDeliveryProxy(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['id' => 'ord-003', 'status' => 'Out for Delivery']),
                'httpCode' => 200,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-003/status');
        $request->getBody()->write(json_encode(['status' => 'Out for Delivery']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-003']);
        $this->assertSame(200, $result->getStatusCode());
    }

    public function testUpdateOrderStatusForwards500FromFunctionApp(): void
    {
        $controller = $this->getMockBuilder(OrderController::class)
            ->onlyMethods(['proxyHttp'])
            ->getMock();

        $controller->method('proxyHttp')
            ->willReturn([
                'body'     => json_encode(['error' => 'Internal server error']),
                'httpCode' => 500,
                'error'    => '',
            ]);

        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);
        $this->assertSame(500, $result->getStatusCode());
    }
}
