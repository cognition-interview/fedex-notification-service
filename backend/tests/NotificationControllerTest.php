<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Controllers\NotificationController;
use FedEx\Database;
use PHPUnit\Framework\TestCase;
use Slim\Psr7\Factory\ServerRequestFactory;
use Slim\Psr7\Response;

class NotificationControllerTest extends TestCase
{
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

    protected function tearDown(): void
    {
        $ref = new \ReflectionProperty(Database::class, 'instance');
        $ref->setAccessible(true);
        $ref->setValue(null, null);
    }

    // ── GET /api/notifications ────────────────────────────────────────────────

    public function testGetNotificationsReturnsAll(): void
    {
        $notifications = [
            ['id' => 'notif-001', 'order_id' => 'ord-001', 'business_id' => 'biz-001',
             'type' => 'Delivery Confirmed', 'message' => 'Package delivered', 'is_read' => false,
             'created_at' => '2026-04-05T14:00:00Z', 'tracking_number' => '7489001',
             'origin' => 'Memphis, TN', 'destination' => 'New York, NY'],
            ['id' => 'notif-002', 'order_id' => 'ord-002', 'business_id' => 'biz-001',
             'type' => 'Status Update', 'message' => 'Package in transit', 'is_read' => true,
             'created_at' => '2026-04-06T09:00:00Z', 'tracking_number' => '7489002',
             'origin' => 'Louisville, KY', 'destination' => 'Chicago, IL'],
        ];

        $listStmt  = $this->mockStmt(null, $notifications);
        $countStmt = $this->mockStmt(null, [], 2);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/notifications');
        $response   = new Response();
        $controller = new NotificationController();

        $result = $controller->getNotifications($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('data', $body);
        $this->assertArrayHasKey('meta', $body);
        $this->assertCount(2, $body['data']);
        $this->assertSame(2, $body['meta']['total']);
    }

    public function testGetNotificationsFilteredByBusinessAndUnread(): void
    {
        $unreadNotifs = [
            ['id' => 'notif-001', 'order_id' => 'ord-001', 'business_id' => 'biz-001',
             'type' => 'Delay Alert', 'message' => 'Package delayed', 'is_read' => false,
             'created_at' => '2026-04-07T06:00:00Z', 'tracking_number' => '7489001',
             'origin' => 'Memphis, TN', 'destination' => 'Dallas, TX'],
        ];

        $listStmt  = $this->mockStmt(null, $unreadNotifs);
        $countStmt = $this->mockStmt(null, [], 1);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($listStmt, $countStmt);
        Database::setTestInstance($pdo);

        $factory  = new ServerRequestFactory();
        $request  = $factory->createServerRequest('GET', '/api/notifications')
            ->withQueryParams(['businessId' => 'biz-001', 'read' => 'false']);
        $response = new Response();

        $result = (new NotificationController())->getNotifications($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertCount(1, $body['data']);
        $this->assertFalse($body['data'][0]['is_read']);
    }

    // ── PATCH /api/notifications/{id}/read ───────────────────────────────────

    public function testMarkNotificationReadTogglesStatus(): void
    {
        $updated = [
            'id' => 'notif-001', 'order_id' => 'ord-001', 'business_id' => 'biz-001',
            'type' => 'Status Update', 'message' => 'Package in transit', 'is_read' => true,
            'created_at' => '2026-04-05T14:00:00Z',
        ];

        $stmt = $this->mockStmt($updated);
        $pdo  = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturn($stmt);
        Database::setTestInstance($pdo);

        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('PATCH', '/api/notifications/notif-001/read');
        $response   = new Response();
        $controller = new NotificationController();

        $result = $controller->markOneRead($request, $response, ['id' => 'notif-001']);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertTrue($body['is_read']);
    }

    public function testMarkNotificationReadReturns404ForMissing(): void
    {
        $stmt = $this->mockStmt(false);
        $pdo  = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturn($stmt);
        Database::setTestInstance($pdo);

        $factory  = new ServerRequestFactory();
        $request  = $factory->createServerRequest('PATCH', '/api/notifications/ghost/read');
        $response = new Response();

        $result = (new NotificationController())->markOneRead($request, $response, ['id' => 'ghost']);

        $this->assertSame(404, $result->getStatusCode());
    }

    public function testMarkAllNotificationsReadRequiresBusinessId(): void
    {
        $pdo = $this->createMock(\PDO::class);
        Database::setTestInstance($pdo);

        $factory  = new ServerRequestFactory();
        $request  = $factory->createServerRequest('PATCH', '/api/notifications/read-all');
        $request->getBody()->write(json_encode([]));
        $response = new Response();

        $result = (new NotificationController())->markAllRead($request, $response);
        $this->assertSame(422, $result->getStatusCode());
    }

    public function testMarkAllNotificationsReadUpdatesRows(): void
    {
        $stmt = $this->createMock(\PDOStatement::class);
        $stmt->method('execute')->willReturn(true);
        $stmt->method('rowCount')->willReturn(5);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturn($stmt);
        Database::setTestInstance($pdo);

        $factory  = new ServerRequestFactory();
        $request  = $factory->createServerRequest('PATCH', '/api/notifications/read-all');
        $request->getBody()->write(json_encode(['businessId' => 'biz-001']));
        $response = new Response();

        $result = (new NotificationController())->markAllRead($request, $response);
        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('updated', $body);
        $this->assertSame(5, $body['updated']);
    }
}
