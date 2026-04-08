<?php

declare(strict_types=1);

namespace FedEx\Controllers;

use FedEx\Database;
use FedEx\Services\EmailService;
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

    public function updateOrderStatus(Request $request, Response $response, array $args): Response
    {
        $body     = (array) json_decode((string) $request->getBody(), true);
        $newStatus = trim($body['status'] ?? '');
        $location  = trim($body['location'] ?? 'Unknown');
        $description = trim($body['description'] ?? '');
        $eventDescription = $description ?: "Status updated to {$newStatus}";

        if (!in_array($newStatus, self::VALID_STATUSES, true)) {
            return $this->json($response, [
                'error'   => 'Invalid status',
                'allowed' => self::VALID_STATUSES,
            ], 422);
        }

        $db = Database::getInstance();

        // Fetch order + business
        $stmt = $db->prepare(
            'SELECT o.*, b.id as business_id, b.name as business_name, b.contact_email
             FROM orders o
             JOIN businesses b ON o.business_id = b.id
             WHERE o.id = :id'
        );
        $stmt->execute([':id' => $args['id']]);
        $order = $stmt->fetch();

        if (!$order) {
            return $this->json($response, ['error' => 'Order not found'], 404);
        }

        // Update status
        $db->prepare(
            "UPDATE orders
             SET status = :status::order_status,
                 actual_delivery = CASE
                   WHEN :status = 'Delivered' THEN NOW()
                   ELSE actual_delivery
                 END,
                 updated_at = NOW()
             WHERE id = :id"
        )->execute([':status' => $newStatus, ':id' => $args['id']]);

        // Insert shipment event
        $eventType = self::STATUS_TO_EVENT[$newStatus] ?? 'In Transit';
        $db->prepare(
            "INSERT INTO shipment_events (id, order_id, event_type, location, description, occurred_at)
             VALUES (gen_random_uuid(), :order_id, :event_type::event_type, :location, :description, NOW())"
        )->execute([
            ':order_id'    => $args['id'],
            ':event_type'  => $eventType,
            ':location'    => $location,
            ':description' => $eventDescription,
        ]);

        // Insert notification row
        $notifType = match ($newStatus) {
            'Delivered'        => 'Delivery Confirmed',
            'Out for Delivery' => 'Out for Delivery',
            'Delayed'          => 'Delay Alert',
            'Exception'        => 'Exception Alert',
            default            => 'Status Update',
        };
        $db->prepare(
            "INSERT INTO notifications (id, order_id, business_id, type, message, is_read, created_at)
             VALUES (gen_random_uuid(), :order_id, :business_id, :type::notification_type, :message, false, NOW())"
        )->execute([
            ':order_id'    => $args['id'],
            ':business_id' => $order['business_id'],
            ':type'        => $notifType,
            ':message'     => "Tracking #{$order['tracking_number']}: status changed to {$newStatus}.",
        ]);

        // Send email (non-blocking)
        try {
            $business = [
                'contact_email' => $order['contact_email'],
                'name'          => $order['business_name'],
            ];
            $sent = (new EmailService())->sendStatusUpdateEmail($order, $business, $newStatus, $eventDescription);
            if (!$sent) {
                error_log('[updateOrderStatus] Email send returned false for order ' . $args['id']);
            }
        } catch (\Throwable $e) {
            error_log('[updateOrderStatus] Email failed: ' . $e->getMessage());
        }

        // Return refreshed order
        return $this->getOrderById($request, $response, $args);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function json(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_UNICODE));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
