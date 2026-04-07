<?php

declare(strict_types=1);

namespace FedEx\Controllers;

use FedEx\Database;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

class BusinessController
{
    // ── GET /api/businesses ───────────────────────────────────────────────────

    public function getBusinesses(Request $request, Response $response): Response
    {
        $p      = $request->getQueryParams();
        $page   = max(1, (int) ($p['page']  ?? 1));
        $limit  = min(100, max(1, (int) ($p['limit'] ?? 10)));
        $offset = ($page - 1) * $limit;

        $db = Database::getInstance();

        $countStmt = $db->query('SELECT COUNT(*) FROM businesses');
        $total     = (int) $countStmt->fetchColumn();

        $stmt = $db->prepare(
            'SELECT * FROM businesses ORDER BY name LIMIT :limit OFFSET :offset'
        );
        $stmt->bindValue(':limit',  $limit,  \PDO::PARAM_INT);
        $stmt->bindValue(':offset', $offset, \PDO::PARAM_INT);
        $stmt->execute();

        return $this->json($response, [
            'businesses' => $stmt->fetchAll(),
            'total'      => $total,
            'page'       => $page,
            'limit'      => $limit,
        ]);
    }

    // ── GET /api/businesses/{id} ──────────────────────────────────────────────

    public function getBusinessById(Request $request, Response $response, array $args): Response
    {
        $db   = Database::getInstance();
        $stmt = $db->prepare(
            "SELECT b.*,
                    COUNT(o.id)                                                       AS total_orders,
                    COUNT(o.id) FILTER (WHERE o.status NOT IN ('Delivered','Exception')) AS active_shipments,
                    COUNT(n.id) FILTER (WHERE n.is_read = false)                      AS unread_notifications
             FROM businesses b
             LEFT JOIN orders o       ON o.business_id = b.id
             LEFT JOIN notifications n ON n.business_id = b.id
             WHERE b.id = :id
             GROUP BY b.id"
        );
        $stmt->execute([':id' => $args['id']]);
        $business = $stmt->fetch();

        if (!$business) {
            return $this->json($response, ['error' => 'Business not found'], 404);
        }

        // Recent orders for this business
        $oStmt = $db->prepare(
            "SELECT id, tracking_number, status, origin, destination, created_at
             FROM orders WHERE business_id = :id ORDER BY created_at DESC LIMIT 10"
        );
        $oStmt->execute([':id' => $args['id']]);
        $business['recent_orders'] = $oStmt->fetchAll();

        return $this->json($response, $business);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function json(Response $response, mixed $data, int $status = 200): Response
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_UNICODE));
        return $response->withHeader('Content-Type', 'application/json')->withStatus($status);
    }
}
