<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Controllers\InsightsController;
use FedEx\Database;
use PHPUnit\Framework\TestCase;
use Slim\Psr7\Factory\ServerRequestFactory;
use Slim\Psr7\Response;

class InsightsControllerTest extends TestCase
{
    protected function tearDown(): void
    {
        $ref = new \ReflectionProperty(Database::class, 'instance');
        $ref->setAccessible(true);
        $ref->setValue(null, null);
    }

    private function mockFetchAllStmt(array $rows): \PDOStatement
    {
        $stmt = $this->createMock(\PDOStatement::class);
        $stmt->method('fetchAll')->willReturn($rows);
        return $stmt;
    }

    private function mockFetchStmt(mixed $row): \PDOStatement
    {
        $stmt = $this->createMock(\PDOStatement::class);
        $stmt->method('fetch')->willReturn($row);
        return $stmt;
    }

    public function testGetInsightsReturnsAllSections(): void
    {
        $avgStmt = $this->mockFetchAllStmt([
            ['service_type' => 'FedEx Overnight', 'avg_hours' => '28.50'],
            ['service_type' => 'FedEx Express', 'avg_hours' => '52.10'],
        ]);
        $onTimeStmt = $this->mockFetchStmt(['on_time_percentage' => '87.3']);
        $volumeStmt = $this->mockFetchAllStmt([
            ['date' => '2026-03-10', 'count' => 45],
            ['date' => '2026-03-11', 'count' => 38],
        ]);
        $routesStmt = $this->mockFetchAllStmt([
            ['origin' => 'New York, NY', 'destination' => 'Los Angeles, CA', 'count' => 120],
        ]);
        $delayStmt = $this->mockFetchAllStmt([
            ['reason' => 'Weather', 'count' => 55],
            ['reason' => 'Address Issue', 'count' => 30],
        ]);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('query')
            ->willReturnOnConsecutiveCalls($avgStmt, $onTimeStmt, $volumeStmt, $routesStmt, $delayStmt);
        Database::setTestInstance($pdo);

        $controller = new InsightsController();
        $request    = (new ServerRequestFactory())->createServerRequest('GET', '/api/insights');
        $response   = new Response();

        $result = $controller->getInsights($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);

        // avg_delivery_time_by_service
        $this->assertArrayHasKey('avg_delivery_time_by_service', $body);
        $this->assertCount(2, $body['avg_delivery_time_by_service']);
        $this->assertSame('FedEx Overnight', $body['avg_delivery_time_by_service'][0]['service_type']);
        $this->assertSame(28.5, $body['avg_delivery_time_by_service'][0]['avg_hours']);
        $this->assertSame(52.1, $body['avg_delivery_time_by_service'][1]['avg_hours']);

        // on_time_percentage
        $this->assertArrayHasKey('on_time_percentage', $body);
        $this->assertSame(87.3, $body['on_time_percentage']);

        // delivery_volume_30d
        $this->assertArrayHasKey('delivery_volume_30d', $body);
        $this->assertCount(2, $body['delivery_volume_30d']);
        $this->assertSame('2026-03-10', $body['delivery_volume_30d'][0]['date']);
        $this->assertSame(45, $body['delivery_volume_30d'][0]['count']);

        // top_routes
        $this->assertArrayHasKey('top_routes', $body);
        $this->assertCount(1, $body['top_routes']);
        $this->assertSame('New York, NY', $body['top_routes'][0]['origin']);
        $this->assertSame('Los Angeles, CA', $body['top_routes'][0]['destination']);
        $this->assertSame(120, $body['top_routes'][0]['count']);

        // delay_breakdown
        $this->assertArrayHasKey('delay_breakdown', $body);
        $this->assertCount(2, $body['delay_breakdown']);
        $this->assertSame('Weather', $body['delay_breakdown'][0]['reason']);
        $this->assertSame(55, $body['delay_breakdown'][0]['count']);
    }

    public function testGetInsightsHandlesEmptyData(): void
    {
        $emptyStmt     = $this->mockFetchAllStmt([]);
        $nullOnTimeStmt = $this->mockFetchStmt(['on_time_percentage' => null]);

        $pdo = $this->createMock(\PDO::class);
        $pdo->method('query')
            ->willReturnOnConsecutiveCalls(
                $emptyStmt,
                $nullOnTimeStmt,
                $this->mockFetchAllStmt([]),
                $this->mockFetchAllStmt([]),
                $this->mockFetchAllStmt([])
            );
        Database::setTestInstance($pdo);

        $controller = new InsightsController();
        $request    = (new ServerRequestFactory())->createServerRequest('GET', '/api/insights');
        $response   = new Response();

        $result = $controller->getInsights($request, $response);

        $this->assertSame(200, $result->getStatusCode());
        $body = json_decode((string) $result->getBody(), true);
        $this->assertEmpty($body['avg_delivery_time_by_service']);
        $this->assertEquals(0, $body['on_time_percentage']);
        $this->assertEmpty($body['delivery_volume_30d']);
        $this->assertEmpty($body['top_routes']);
        $this->assertEmpty($body['delay_breakdown']);
    }
}
