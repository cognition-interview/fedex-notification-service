<?php

declare(strict_types=1);

namespace FedEx\Controllers;

use FedEx\Database;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

class NotificationController
{
    // ── GET /api/notifications ────────────────────────────────────────────────

    public function getNotifications(Request $request, Response $response): Response
    {
        $p      = $request->getQueryParams();
        $page   = max(1, (int) ($p['page']  ?? 1));
        $limit  = min(100, max(1, (int) ($p['limit'] ?? 10)));
        $offset = ($page - 1) * $limit;

        $where  = ['1=1'];
        $params = [];

        if (!empty($p['businessId'])) {
            $where[]               = 'n.business_id = :businessId';
            $params[':businessId'] = $p['businessId'];
        }
        if (isset($p['read']) && $p['read'] !== '') {
            $where[]        = 'n.is_read = :read';
            $params[':read'] = filter_var($p['read'], FILTER_VALIDATE_BOOLEAN) ? 'true' : 'false';
        }

        $db  = Database::getInstance();
        $sql = 'SELECT n.*, o.tracking_number, o.origin, o.destination
                FROM notifications n
                JOIN orders o ON n.order_id = o.id
                WHERE ' . implode(' AND ', $where) . '
                ORDER BY n.created_at DESC
                LIMIT :limit OFFSET :offset';

        $stmt = $db->prepare($sql);
        foreach ($params as $k => $v) {
            $stmt->bindValue($k, $v);
        }
        $stmt->bindValue(':limit',  $limit,  \PDO::PARAM_INT);
        $stmt->bindValue(':offset', $offset, \PDO::PARAM_INT);
        $stmt->execute();
        $notifications = $stmt->fetchAll();

        $countStmt = $db->prepare(
            'SELECT COUNT(*) FROM notifications n WHERE ' . implode(' AND ', $where)
        );
        foreach ($params as $k => $v) {
            $countStmt->bindValue($k, $v);
        }
        $countStmt->execute();
        $total = (int) $countStmt->fetchColumn();

        return $this->json($response, [
            'notifications' => $notifications,
            'total'         => $total,
            'page'          => $page,
            'limit'         => $limit,
        ]);
    }

    // ── PATCH /api/notifications/{id}/read ───────────────────────────────────

    public function markOneRead(Request $request, Response $response, array $args): Response
    {
        $db   = Database::getInstance();
        $stmt = $db->prepare(
            'UPDATE notifications SET is_read = true WHERE id = :id RETURNING *'
        );
        $stmt->execute([':id' => $args['id']]);
        $notification = $stmt->fetch();

        if (!$notification) {
            return $this->json($response, ['error' => 'Notification not found'], 404);
        }

        return $this->json($response, $notification);
    }

    // ── PATCH /api/notifications/read-all ────────────────────────────────────

    public function markAllRead(Request $request, Response $response): Response
    {
        $body       = (array) json_decode((string) $request->getBody(), true);
        $businessId = trim($body['businessId'] ?? '');
        $db   = Database::getInstance();
        if ($businessId) {
            $stmt = $db->prepare(
                'UPDATE notifications SET is_read = true WHERE business_id = :businessId AND is_read = false'
            );
            $stmt->execute([':businessId' => $businessId]);
        } else {
            $stmt = $db->prepare(
                'UPDATE notifications SET is_read = true WHERE is_read = false'
            );
            $stmt->execute();
        }

        return $this->json($response, ['updated' => $stmt->rowCount()]);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function json(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_UNICODE));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
