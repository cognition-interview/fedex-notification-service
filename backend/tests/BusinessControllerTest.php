<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Controllers\BusinessController;
use FedEx\Database;
use PHPUnit\Framework\TestCase;
use Slim\Psr7\Factory\ServerRequestFactory;
use Slim\Psr7\Response;

class BusinessControllerTest extends TestCase
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

    // ── GET /api/businesses ──────────────────────────────────────────────────

    public function testGetBusinessesReturnsPaginatedList(): void
    {
        $businesses = [
            ['id' => 'biz-001', 'name' => 'Acme Corp', 'account_number' => 'ACC-0001',
             'address' => '123 Main St', 'contact_email' => 'test@acme.com', 'phone' => '+1-555-0001'],
            ['id' => 'biz-002', 'name' => 'Beta Inc', 'account_number' => 'ACC-0002',
             'address' => '456 Oak Ave', 'contact_email' => 'test@beta.com', 'phone' => '+1-555-0002'],
        ];

        $countStmt = $this->mockStmt(null, [], 2);
        $listStmt  = $this->mockStmt(null, $businesses);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('query')->willReturn($countStmt);
        $pdo->method('prepare')->willReturn($listStmt);
        Database::setTestInstance($pdo);

        $controller = new BusinessController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/businesses');
        $response   = new Response();

        $result = $controller->getBusinesses($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('businesses', $body);
        $this->assertArrayHasKey('total', $body);
        $this->assertCount(2, $body['businesses']);
        $this->assertSame(2, $body['total']);
        $this->assertSame(1, $body['page']);
        $this->assertSame(10, $body['limit']);
    }

    public function testGetBusinessesRespectsPagination(): void
    {
        $countStmt = $this->mockStmt(null, [], 50);
        $listStmt  = $this->mockStmt(null, []);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('query')->willReturn($countStmt);
        $pdo->method('prepare')->willReturn($listStmt);
        Database::setTestInstance($pdo);

        $controller = new BusinessController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/businesses')
            ->withQueryParams(['page' => '3', 'limit' => '5']);
        $response   = new Response();

        $result = $controller->getBusinesses($request, $response);
        $body   = json_decode((string) $result->getBody(), true);
        $this->assertSame(3, $body['page']);
        $this->assertSame(5, $body['limit']);
        $this->assertSame(50, $body['total']);
    }

    public function testGetBusinessesClampsPaginationBounds(): void
    {
        $countStmt = $this->mockStmt(null, [], 0);
        $listStmt  = $this->mockStmt(null, []);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('query')->willReturn($countStmt);
        $pdo->method('prepare')->willReturn($listStmt);
        Database::setTestInstance($pdo);

        $controller = new BusinessController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/businesses')
            ->withQueryParams(['page' => '-1', 'limit' => '200']);
        $response   = new Response();

        $result = $controller->getBusinesses($request, $response);
        $body   = json_decode((string) $result->getBody(), true);
        $this->assertSame(1, $body['page']);
        $this->assertSame(100, $body['limit']);
    }

    // ── GET /api/businesses/{id} ─────────────────────────────────────────────

    public function testGetBusinessByIdReturnsBusinessWithStats(): void
    {
        $business = [
            'id' => 'biz-001', 'name' => 'Acme Corp', 'account_number' => 'ACC-0001',
            'total_orders' => 25, 'active_shipments' => 5, 'unread_notifications' => 3,
        ];
        $recentOrders = [
            ['id' => 'ord-001', 'tracking_number' => 'TRK001', 'status' => 'In Transit',
             'origin' => 'Memphis, TN', 'destination' => 'New York, NY', 'created_at' => '2026-04-01'],
        ];

        $bizStmt    = $this->mockStmt($business);
        $ordersStmt = $this->mockStmt(null, $recentOrders);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturnOnConsecutiveCalls($bizStmt, $ordersStmt);
        Database::setTestInstance($pdo);

        $controller = new BusinessController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/businesses/biz-001');
        $response   = new Response();

        $result = $controller->getBusinessById($request, $response, ['id' => 'biz-001']);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertSame('biz-001', $body['id']);
        $this->assertSame('Acme Corp', $body['name']);
        $this->assertArrayHasKey('recent_orders', $body);
        $this->assertCount(1, $body['recent_orders']);
        $this->assertSame(25, $body['total_orders']);
        $this->assertSame(5, $body['active_shipments']);
        $this->assertSame(3, $body['unread_notifications']);
    }

    public function testGetBusinessByIdReturns404ForMissing(): void
    {
        $bizStmt = $this->mockStmt(false);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('prepare')->willReturn($bizStmt);
        Database::setTestInstance($pdo);

        $controller = new BusinessController();
        $factory    = new ServerRequestFactory();
        $request    = $factory->createServerRequest('GET', '/api/businesses/nonexistent');
        $response   = new Response();

        $result = $controller->getBusinessById($request, $response, ['id' => 'nonexistent']);

        $this->assertSame(404, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertArrayHasKey('error', $body);
        $this->assertSame('Business not found', $body['error']);
    }
}
