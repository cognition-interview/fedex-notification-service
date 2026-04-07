<?php

declare(strict_types=1);

namespace FedEx\Services;

class EmailService
{
    private string $endpoint;
    private string $accessKey;
    private string $fromAddress;

    public function __construct()
    {
        $connStr = $_ENV['AZURE_EMAIL_CONNECTION_STRING'] ?? '';
        $this->parseConnectionString($connStr);
        $this->fromAddress = $_ENV['AZURE_EMAIL_FROM_ADDRESS'] ?? '';
    }

    private function parseConnectionString(string $connStr): void
    {
        preg_match('/endpoint=(https?:\/\/[^;]+)/i', $connStr, $endpointMatch);
        preg_match('/accesskey=([^;]+)/i', $connStr, $keyMatch);

        $this->endpoint   = rtrim($endpointMatch[1] ?? '', '/');
        $this->accessKey  = $keyMatch[1] ?? '';
    }

    /**
     * Send a status-update email to a business contact.
     *
     * @param array $order    Keys: tracking_number, origin, destination
     * @param array $business Keys: contact_email, name
     * @param string $newStatus
     */
    public function sendStatusUpdateEmail(array $order, array $business, string $newStatus, ?string $eventDescription = null): bool
    {
        $to      = $business['contact_email'];
        $subject = "FedEx Update: Tracking #{$order['tracking_number']} — {$newStatus}";
        $desc    = trim((string) ($eventDescription ?? ''));

        $plainText = implode("\n", [
            "Hello {$business['name']},",
            "",
            "Your shipment status has been updated.",
            "",
            "Tracking Number : {$order['tracking_number']}",
            "Route           : {$order['origin']} → {$order['destination']}",
            "New Status      : {$newStatus}",
            $desc !== '' ? "Description     : {$desc}" : "Description     : Status updated to {$newStatus}",
            "Updated At      : " . gmdate('D, d M Y H:i:s') . " UTC",
            "",
            "This is an automated message from FedEx Notification Service.",
        ]);

        $html = "
            <div style='font-family:Arial,sans-serif;color:#333;max-width:600px'>
                <div style='background:#4D148C;padding:16px 24px'>
                    <span style='color:#FF6200;font-size:24px;font-weight:bold'>Fed</span><span style='color:#fff;font-size:24px;font-weight:bold'>Ex</span>
                </div>
                <div style='padding:24px;border:1px solid #ddd'>
                    <p>Hello <strong>{$business['name']}</strong>,</p>
                    <p>Your shipment status has been updated.</p>
                    <table style='width:100%;border-collapse:collapse;margin:16px 0'>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Tracking Number</td><td style='padding:8px'>{$order['tracking_number']}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Route</td><td style='padding:8px'>{$order['origin']} → {$order['destination']}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>New Status</td><td style='padding:8px;color:#4D148C;font-weight:bold'>{$newStatus}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Description</td><td style='padding:8px'>" . ($desc !== '' ? htmlspecialchars($desc, ENT_QUOTES, 'UTF-8') : "Status updated to {$newStatus}") . "</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Updated At</td><td style='padding:8px'>" . gmdate('D, d M Y H:i:s') . " UTC</td></tr>
                    </table>
                    <p style='font-size:12px;color:#999'>This is an automated message from FedEx Notification Service. Do not reply.</p>
                </div>
            </div>";

        $body = json_encode([
            'sender' => $this->fromAddress,
            'recipients' => ['to' => [['email' => $to]]],
            'content' => [
                'subject'   => $subject,
                'plainText' => $plainText,
                'html'      => $html,
            ],
        ]);

        return $this->post('/emails:send?api-version=2021-10-01-preview', $body);
    }

    protected function post(string $path, string $body): bool
    {
        $host        = parse_url($this->endpoint, PHP_URL_HOST);
        $date        = gmdate('D, d M Y H:i:s') . ' GMT';
        $contentHash = base64_encode(hash('sha256', $body, true));
        $signature   = $this->buildSignature('POST', $path, $date, $host, $contentHash);

        $repeatabilityId = sprintf(
            '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
            mt_rand(0, 0xffff), mt_rand(0, 0xffff),
            mt_rand(0, 0xffff),
            mt_rand(0, 0x0fff) | 0x4000,
            mt_rand(0, 0x3fff) | 0x8000,
            mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
        );

        $headers = [
            'Content-Type: application/json',
            "x-ms-date: {$date}",
            "x-ms-content-sha256: {$contentHash}",
            "Authorization: HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={$signature}",
            "Repeatability-Request-ID: {$repeatabilityId}",
            "Repeatability-First-Sent: {$date}",
        ];

        $ch = curl_init($this->endpoint . $path);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_HTTPHEADER     => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 15,
        ]);

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr  = curl_error($ch);
        curl_close($ch);

        if ($curlErr) {
            error_log("[EmailService] curl error: {$curlErr}");
            return false;
        }

        if ($httpCode < 200 || $httpCode >= 300) {
            error_log("[EmailService] Azure returned HTTP {$httpCode}: {$response}");
            return false;
        }

        error_log("[EmailService] Azure accepted request HTTP {$httpCode}: {$response}");

        return true;
    }

    private function buildSignature(
        string $method,
        string $path,
        string $date,
        string $host,
        string $contentHash
    ): string {
        $stringToSign = "{$method}\n{$path}\n{$date};{$host};{$contentHash}";
        return base64_encode(
            hash_hmac('sha256', $stringToSign, base64_decode($this->accessKey), true)
        );
    }
}
