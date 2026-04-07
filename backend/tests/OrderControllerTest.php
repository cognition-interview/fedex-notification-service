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
        $this->assertArrayHasKey('data', $body);
        $this->assertArrayHasKey('meta', $body);
        $this->assertCount(2, $body['data']);
        $this->assertSame(2, $body['meta']['total']);
        $this->assertSame(1, $body['meta']['page']);
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
        $this->assertSame(0, $body['meta']['total']);
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
        $this->assertSame(3, $body['meta']['page']);
        $this->assertSame(5, $body['meta']['limit']);
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
        $this->assertArrayHasKey('events', $body);
        $this->assertCount(1, $body['events']);
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

    // ── PATCH /api/orders/{id}/status ─────────────────────────────────────────

    public function testUpdateOrderStatusInvalidReturns422(): void
    {
        $pdo = $this->mockPdo();
        Database::setTestInstance($pdo);

        $controller = new OrderController();

        // Build a request with an invalid status
        $factory = new ServerRequestFactory();
        $request = $factory->createServerRequest('PATCH', '/api/orders/ord-001/status');
        $request->getBody()->write(json_encode(['status' => 'Flying']));

        $response = new Response();
        $result   = $controller->updateOrderStatus($request, $response, ['id' => 'ord-001']);

        $this->assertSame(422, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('error', $body);
        $this->assertArrayHasKey('allowed', $body);
        $this->assertContains('In Transit', $body['allowed']);
    }

    public function testUpdateOrderStatusValidUpdatesOrderAndInsertsEvent(): void
    {
        $order = [
            'id' => 'ord-002', 'tracking_number' => '7489002', 'status' => 'Picked Up',
            'origin' => 'Memphis, TN', 'destination' => 'New York, NY',
            'business_id' => 'biz-001', 'business_name' => 'Acme', 'contact_email' => 'gb555@cornell.edu',
            'weight_lbs' => 5.0, 'service_type' => 'Ground',
            'estimated_delivery' => '2026-04-10T17:00:00Z', 'actual_delivery' => null,
            'created_at' => '2026-04-07T00:00:00Z', 'updated_at' => '2026-04-07T00:00:00Z',
        ];

        // Stmts for: fetch order, update status, insert event, insert notification, then getOrderById (fetch order + fetch events)
        $fetchOrderStmt  = $this->mockStmt($order);
        $updateStmt      = $this->mockStmt();
        $insertEvtStmt   = $this->mockStmt();
        $insertNotifStmt = $this->mockStmt();
        // getOrderById calls: fetch order again, fetch events
        $fetchOrder2Stmt = $this->mockStmt($order);
        $fetchEvtsStmt   = $this->mockStmt(null, []);

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturnOnConsecutiveCalls(
            $fetchOrderStmt, $updateStmt, $insertEvtStmt, $insertNotifStmt,
            $fetchOrder2Stmt, $fetchEvtsStmt
        );
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('PATCH', '/api/orders/ord-002/status');
        $request->getBody()->write(json_encode([
            'status'      => 'In Transit',
            'location'    => 'Nashville, TN',
            'description' => 'Package departed hub',
        ]));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ord-002']);

        $this->assertSame(200, $result->getStatusCode());
    }

    public function testUpdateOrderStatusReturns404ForMissingOrder(): void
    {
        $fetchStmt = $this->mockStmt(false); // order not found

        $pdo = $this->mockPdo();
        $pdo->method('prepare')->willReturn($fetchStmt);
        Database::setTestInstance($pdo);

        $controller = new OrderController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('PATCH', '/api/orders/ghost/status');
        $request->getBody()->write(json_encode(['status' => 'In Transit']));
        $response = new Response();

        $result = $controller->updateOrderStatus($request, $response, ['id' => 'ghost']);

        $this->assertSame(404, $result->getStatusCode());
    }
}
