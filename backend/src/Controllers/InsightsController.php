<?php

declare(strict_types=1);

namespace FedEx\Controllers;

use FedEx\Database;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

class InsightsController
{
    // ── GET /api/insights ────────────────────────────────────────────────────

    public function getInsights(Request $request, Response $response): Response
    {
        $db = Database::getInstance();

        $avgByService = $db->query(
            "SELECT service_type::text AS service_type,
                    ROUND(
                        AVG(
                            GREATEST(EXTRACT(EPOCH FROM (actual_delivery::timestamp - created_at)), 0) / 3600.0
                        )::numeric,
                        2
                    ) AS avg_hours
             FROM orders
             WHERE actual_delivery IS NOT NULL
             GROUP BY service_type
             ORDER BY avg_hours ASC"
        )->fetchAll();

        $onTimeRow = $db->query(
            "SELECT COALESCE(
                        ROUND(
                            100.0 * COUNT(*) FILTER (
                                WHERE actual_delivery IS NOT NULL
                                  AND estimated_delivery IS NOT NULL
                                  AND actual_delivery <= estimated_delivery
                            )
                            / NULLIF(COUNT(*) FILTER (
                                WHERE actual_delivery IS NOT NULL
                                  AND estimated_delivery IS NOT NULL
                            ), 0),
                            1
                        ),
                        0
                    ) AS on_time_percentage
             FROM orders"
        )->fetch();

        $volume30d = $db->query(
            "SELECT to_char(day_series.day::date, 'YYYY-MM-DD') AS date,
                    COALESCE(delivered.count, 0)::int AS count
             FROM generate_series(
                CURRENT_DATE - INTERVAL '29 days',
                CURRENT_DATE,
                INTERVAL '1 day'
             ) AS day_series(day)
             LEFT JOIN (
                SELECT actual_delivery::date AS delivery_date, COUNT(*)::int AS count
                FROM orders
                WHERE actual_delivery IS NOT NULL
                  AND actual_delivery >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY actual_delivery::date
             ) delivered ON delivered.delivery_date = day_series.day::date
             ORDER BY day_series.day ASC"
        )->fetchAll();

        $topRoutes = $db->query(
            "SELECT origin, destination, COUNT(*)::int AS count
             FROM orders
             GROUP BY origin, destination
             ORDER BY count DESC
             LIMIT 5"
        )->fetchAll();

        $delayBreakdown = $db->query(
            "SELECT reason, COUNT(*)::int AS count
             FROM (
                SELECT CASE
                    WHEN se.description ILIKE '%weather%' THEN 'Weather'
                    WHEN se.description ILIKE '%address%' THEN 'Address Issue'
                    WHEN se.description ILIKE '%custom%' THEN 'Customs Hold'
                    WHEN se.description ILIKE '%volume%' THEN 'Volume Surge'
                    WHEN se.description ILIKE '%vehicle%' THEN 'Vehicle Breakdown'
                    WHEN se.event_type = 'Delay Reported'::event_type THEN 'Delay Reported'
                    WHEN se.event_type = 'Exception'::event_type THEN 'Exception'
                    ELSE 'Other'
                END AS reason
                FROM shipment_events se
                WHERE se.event_type IN (
                    'Delay Reported'::event_type,
                    'Exception'::event_type,
                    'Delivery Attempted'::event_type
                )
             ) t
             GROUP BY reason
             ORDER BY count DESC
             LIMIT 5"
        )->fetchAll();

        $payload = [
            'avg_delivery_time_by_service' => array_map(
                fn (array $row): array => [
                    'service_type' => (string) $row['service_type'],
                    'avg_hours'    => round((float) $row['avg_hours'], 2),
                ],
                $avgByService
            ),
            'on_time_percentage' => round((float) ($onTimeRow['on_time_percentage'] ?? 0), 1),
            'delivery_volume_30d' => array_map(
                fn (array $row): array => [
                    'date'  => (string) $row['date'],
                    'count' => (int) $row['count'],
                ],
                $volume30d
            ),
            'top_routes' => array_map(
                fn (array $row): array => [
                    'origin'      => (string) $row['origin'],
                    'destination' => (string) $row['destination'],
                    'count'       => (int) $row['count'],
                ],
                $topRoutes
            ),
            'delay_breakdown' => array_map(
                fn (array $row): array => [
                    'reason' => (string) $row['reason'],
                    'count'  => (int) $row['count'],
                ],
                $delayBreakdown
            ),
        ];

        return $this->json($response, $payload);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function json(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_UNICODE));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
