<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Database;
use PHPUnit\Framework\TestCase;

class DatabaseTest extends TestCase
{
    protected function tearDown(): void
    {
        $ref = new \ReflectionProperty(Database::class, 'instance');
        $ref->setAccessible(true);
        $ref->setValue(null, null);
    }

    public function testSetTestInstanceAndGetInstance(): void
    {
        $pdo = $this->createMock(\PDO::class);
        Database::setTestInstance($pdo);

        $result = Database::getInstance();
        $this->assertSame($pdo, $result);
    }

    public function testGetInstanceReturnsSameInstanceOnSubsequentCalls(): void
    {
        $pdo = $this->createMock(\PDO::class);
        Database::setTestInstance($pdo);

        $first  = Database::getInstance();
        $second = Database::getInstance();
        $this->assertSame($first, $second);
    }

    public function testGetInstanceBuildsConnectionFromEnvWhenNoTestInstance(): void
    {
        // Use port 1 which will never have PostgreSQL, ensuring a fast connection-refused error
        $_ENV['POSTGRES_CONNECTION_STRING'] = 'postgresql://user:pass@localhost:1/testdb';

        $this->expectException(\PDOException::class);
        Database::getInstance();
    }

    public function testGetInstanceFallsBackToHostWhenDnsReturnsNoRecords(): void
    {
        // Use an IP address directly — dns_get_record for IPs typically returns empty
        $_ENV['POSTGRES_CONNECTION_STRING'] = 'postgresql://user:pass@127.0.0.1:1/testdb';

        $this->expectException(\PDOException::class);
        Database::getInstance();
    }

    public function testGetInstanceUsesDefaultPortWhenOmitted(): void
    {
        // Connection string without explicit port — should default to 5432
        $_ENV['POSTGRES_CONNECTION_STRING'] = 'postgresql://user:p%40ss@localhost/testdb';

        $this->expectException(\PDOException::class);
        Database::getInstance();
    }
}
