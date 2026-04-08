<?php

declare(strict_types=1);

namespace FedEx\Controllers;

use FedEx\Database;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

class OrderController
{
    private const VALID_STATUSES = [
        'Picked Up', 'In Transit', 'Out for Delivery', 'Delivered', 'Delayed', 'Exception',
    ];

    private const STATUS_TO_EVENT = [
        'Picked Up'        => 'Package Picked Up',
        'In Transit'       => 'In Transit',
        'Out for Delivery' => 'Out for Delivery',
        'Delivered'        => 'Delivered',
        'Delayed'          => 'Delay Reported',
        'Exception'        => 'Exception',
    ];

    // ── GET /api/orders ───────────────────────────────────────────────────────

    public function getOrders(Request $request, Response $response): Response
    {
        $p = $request->getQueryParams();
        $page  = max(1, (int) ($p['page']  ?? 1));
        $limit = min(100, max(1, (int) ($p['limit'] ?? 10)));
        $offset = ($page - 1) * $limit;

        $where  = ['1=1'];
        $params = [];

        if (!empty($p['businessId'])) {
            $where[]                  = 'o.business_id = :businessId';
            $params[':businessId']    = $p['businessId'];
        }
        if (!empty($p['status'])) {
            $where[]           = "o.status = :status::order_status";
            $params[':status'] = $p['status'];
        }
        $serviceType = $p['serviceType'] ?? $p['service_type'] ?? null;
        if (!empty($serviceType)) {
            $where[]                = "o.service_type = :serviceType::service_type";
            $params[':serviceType'] = $serviceType;
        }
        if (!empty($p['fromDate'])) {
            $where[]              = 'o.created_at >= :fromDate';
            $params[':fromDate']  = $p['fromDate'];
        }
        if (!empty($p['toDate'])) {
            $where[]            = 'o.created_at <= :toDate';
            $params[':toDate']  = $p['toDate'];
        }
        if (!empty($p['search'])) {
            $search = trim((string) $p['search']);
            $where[] = '(o.tracking_number ILIKE :search
                        OR REPLACE(o.tracking_number, \' \', \'\') ILIKE :searchNoSpace
                        OR o.origin ILIKE :search
                        OR o.destination ILIKE :search)';
            $params[':search'] = '%' . $search . '%';
            $params[':searchNoSpace'] = '%' . str_replace(' ', '', $search) . '%';
        }

        $sql = 'SELECT o.id, o.tracking_number, o.origin, o.destination, o.status,
                       o.weight_lbs, o.service_type, o.estimated_delivery, o.actual_delivery,
                       o.created_at, o.updated_at,
                       b.id as business_id, b.name as business_name
                FROM orders o
                JOIN businesses b ON o.business_id = b.id
                WHERE ' . implode(' AND ', $where) . '
                ORDER BY o.created_at DESC
                LIMIT :limit OFFSET :offset';

        $db   = Database::getInstance();
        $stmt = $db->prepare($sql);
        foreach ($params as $k => $v) {
            $stmt->bindValue($k, $v);
        }
        $stmt->bindValue(':limit',  $limit,  \PDO::PARAM_INT);
        $stmt->bindValue(':offset', $offset, \PDO::PARAM_INT);
        $stmt->execute();
        $orders = $stmt->fetchAll();

        // Total count
        $countSql  = 'SELECT COUNT(*) FROM orders o WHERE ' . implode(' AND ', $where);
        $countStmt = $db->prepare($countSql);
        foreach ($params as $k => $v) {
            $countStmt->bindValue($k, $v);
        }
        $countStmt->execute();
        $total = (int) $countStmt->fetchColumn();

        return $this->json($response, [
            'orders' => $orders,
            'total'  => $total,
            'page'   => $page,
            'limit'  => $limit,
        ]);
    }

    // ── GET /api/orders/stats ─────────────────────────────────────────────────

    public function getOrderStats(Request $request, Response $response): Response
    {
        $p          = $request->getQueryParams();
        $where      = ['1=1'];
        $params     = [];

        if (!empty($p['businessId'])) {
            $where[]               = 'business_id = :businessId';
            $params[':businessId'] = $p['businessId'];
        }

        $w   = implode(' AND ', $where);
        $db  = Database::getInstance();

        $statsSql = "SELECT
            COUNT(*)                                                      AS total,
            COUNT(*) FILTER (WHERE status = 'Picked Up')                  AS picked_up,
            COUNT(*) FILTER (WHERE status = 'In Transit')                 AS in_transit,
            COUNT(*) FILTER (WHERE status = 'Out for Delivery')           AS out_for_delivery,
            COUNT(*) FILTER (WHERE status = 'Delivered')                  AS delivered,
            COUNT(*) FILTER (WHERE status = 'Delayed')                    AS delayed,
            COUNT(*) FILTER (WHERE status = 'Exception')                  AS exception
          FROM orders WHERE {$w}";

        $stmt = $db->prepare($statsSql);
        foreach ($params as $k => $v) {
            $stmt->bindValue($k, $v);
        }
        $stmt->execute();
        $stats = $stmt->fetch();

        // Recent 10 orders
        $recentSql = "SELECT o.id, o.tracking_number, o.status, o.origin, o.destination,
                             o.created_at, b.name as business_name
                      FROM orders o
                      JOIN businesses b ON o.business_id = b.id
                      WHERE {$w}
                      ORDER BY o.created_at DESC LIMIT 10";

        $recentStmt = $db->prepare($recentSql);
        foreach ($params as $k => $v) {
            $recentStmt->bindValue($k, $v);
        }
        $recentStmt->execute();
        $recent = $recentStmt->fetchAll();

        // Unread notification count
        $nWhere  = ['1=1'];
        $nParams = [];
        if (!empty($p['businessId'])) {
            $nWhere[]              = 'business_id = :businessId';
            $nParams[':businessId'] = $p['businessId'];
        }
        $nSql  = 'SELECT COUNT(*) FROM notifications WHERE is_read = false AND ' . implode(' AND ', $nWhere);
        $nStmt = $db->prepare($nSql);
        foreach ($nParams as $k => $v) {
            $nStmt->bindValue($k, $v);
        }
        $nStmt->execute();
        $unread = (int) $nStmt->fetchColumn();

        return $this->json($response, [
            'by_status'            => array_map('intval', $stats),
            'recent_orders'        => $recent,
            'unread_notifications' => $unread,
        ]);
    }

    // ── GET /api/orders/{id} ──────────────────────────────────────────────────

    public function getOrderById(Request $request, Response $response, array $args): Response
    {
        $db = Database::getInstance();

        $stmt = $db->prepare(
            'SELECT o.*, b.name as business_name, b.contact_email, b.id as business_id
             FROM orders o
             JOIN businesses b ON o.business_id = b.id
             WHERE o.id = :id'
        );
        $stmt->execute([':id' => $args['id']]);
        $order = $stmt->fetch();

        if (!$order) {
            return $this->json($response, ['error' => 'Order not found'], 404);
        }

        $evtStmt = $db->prepare(
            'SELECT * FROM shipment_events WHERE order_id = :id ORDER BY occurred_at DESC'
        );
        $evtStmt->execute([':id' => $args['id']]);
        $order['shipment_events'] = $evtStmt->fetchAll();

        return $this->json($response, $order);
    }

    // ── PATCH /api/orders/{id}/status ─────────────────────────────────────────
    //
    // Proxies the request to the Azure Function App (fedex-update-status).
    // The Function App performs all side effects: DB update, shipment event,
    // notification, and email. This endpoint simply forwards the request and
    // returns the Function App's response.

    public function updateOrderStatus(Request $request, Response $response, array $args): Response
    {
        $functionUrl = $_ENV['AZURE_FUNCTION_APP_URL'] ?? '';
        $functionKey = $_ENV['AZURE_FUNCTION_APP_KEY'] ?? '';

        if ($functionUrl === '' || $functionKey === '') {
            error_log('[updateOrderStatus] AZURE_FUNCTION_APP_URL or AZURE_FUNCTION_APP_KEY not configured');
            return $this->json($response, [
                'error' => 'Function App not configured',
            ], 503);
        }

        $orderId = $args['id'];
        $url = rtrim($functionUrl, '/') . "/api/orders/{$orderId}/status?code=" . urlencode($functionKey);

        $requestBody = (string) $request->getBody();

        /** @var array{body: string|false, httpCode: int, error: string} */
        $result = $this->proxyHttp('PATCH', $url, $requestBody);

        if ($result['body'] === false || $result['error'] !== '') {
            error_log("[updateOrderStatus] Proxy error: {$result['error']}");
            return $this->json($response, [
                'error' => 'Failed to reach Function App',
            ], 502);
        }

        // Forward the Function App's response as-is
        $response->getBody()->write($result['body']);
        return $response
            ->withHeader('Content-Type', 'application/json')
            ->withStatus($result['httpCode']);
    }

    /**
     * Make an HTTP request to the Azure Function App.
     * Extracted so tests can override without needing real network access.
     *
     * @return array{body: string|false, httpCode: int, error: string}
     */
    protected function proxyHttp(string $method, string $url, string $body): array
    {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST  => $method,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER     => [
                'Content-Type: application/json',
                'Accept: application/json',
            ],
            CURLOPT_TIMEOUT        => 30,
            CURLOPT_CONNECTTIMEOUT => 10,
        ]);

        $responseBody = curl_exec($ch);
        $httpCode     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlError    = curl_error($ch);
        curl_close($ch);

        return [
            'body'     => $responseBody,
            'httpCode' => $httpCode,
            'error'    => $curlError,
        ];
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function json(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_UNICODE));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
