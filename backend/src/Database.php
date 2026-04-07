<?php

declare(strict_types=1);

namespace FedEx;

use PDO;

class Database
{
    private static ?PDO $instance = null;

    public static function setTestInstance(PDO $pdo): void
    {
        self::$instance = $pdo;
    }

    public static function getInstance(): PDO
    {
        if (self::$instance === null) {
            $url = parse_url($_ENV['POSTGRES_CONNECTION_STRING']);

            $host = $url['host'];

            // Docker containers often lack IPv6 routing, so DNS resolving to an AAAA
            // record causes "Network unreachable". Force IPv4 by resolving to an A record
            // and passing it as hostaddr (libpq uses hostaddr for the actual TCP connect
            // but still sends host as the SNI/TLS server name for SSL verification).
            $records = dns_get_record($host, DNS_A);
            $ipv4 = !empty($records) ? $records[0]['ip'] : $host;

            $dsn = sprintf(
                'pgsql:host=%s;hostaddr=%s;port=%d;dbname=%s;sslmode=require',
                $host,
                $ipv4,
                $url['port'] ?? 5432,
                ltrim($url['path'], '/')
            );

            self::$instance = new PDO(
                $dsn,
                $url['user'],
                urldecode($url['pass']),
                [
                    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                ]
            );
        }

        return self::$instance;
    }
}
