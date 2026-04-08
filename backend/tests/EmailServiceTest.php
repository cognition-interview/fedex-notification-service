<?php

declare(strict_types=1);

namespace FedEx\Tests;

use FedEx\Services\EmailService;
use PHPUnit\Framework\TestCase;

/**
 * Testable subclass — overrides the protected post() method so we can
 * inspect the JSON body and auth header without making real HTTP calls.
 */
class TestableEmailService extends EmailService
{
    public ?string $lastPath = null;
    public ?string $lastBody = null;
    public bool $postReturn  = true;

    /** @var array<string,string> */
    public array $lastHeaders = [];

    protected function post(string $path, string $body): bool
    {
        $this->lastPath = $path;
        $this->lastBody = $body;
        return $this->postReturn;
    }
}

class EmailServiceTest extends TestCase
{
    private TestableEmailService $service;
    private string $origConnStr;
    private string $origFromAddr;

    protected function setUp(): void
    {
        // Preserve bootstrap values so they can be restored for subsequent test files
        $this->origConnStr  = $_ENV['AZURE_EMAIL_CONNECTION_STRING'] ?? '';
        $this->origFromAddr = $_ENV['AZURE_EMAIL_FROM_ADDRESS'] ?? '';

        $_ENV['AZURE_EMAIL_CONNECTION_STRING'] =
            'endpoint=https://test.communication.azure.com;accesskey=' . base64_encode('test-access-key');
        $_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'noreply@fedex-test.com';

        $this->service = new TestableEmailService();
    }

    protected function tearDown(): void
    {
        $_ENV['AZURE_EMAIL_CONNECTION_STRING'] = $this->origConnStr;
        $_ENV['AZURE_EMAIL_FROM_ADDRESS']      = $this->origFromAddr;
    }

    private function makeOrder(array $overrides = []): array
    {
        return array_merge([
            'tracking_number' => '748923014456',
            'origin'          => 'Memphis, TN',
            'destination'     => 'New York, NY',
        ], $overrides);
    }

    private function makeBusiness(array $overrides = []): array
    {
        return array_merge([
            'contact_email' => 'gb555@cornell.edu',
            'name'          => 'Acme Electronics',
        ], $overrides);
    }

    public function testSendStatusUpdateEmailReturnsTrueOnSuccess(): void
    {
        $this->service->postReturn = true;

        $result = $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'In Transit'
        );

        $this->assertTrue($result);
    }

    public function testSendStatusUpdateEmailCallsCorrectEndpoint(): void
    {
        $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'Delivered'
        );

        $this->assertStringContainsString('/emails:send', $this->service->lastPath);
        $this->assertStringContainsString('api-version=', $this->service->lastPath);
    }

    public function testSendStatusUpdateEmailBodyContainsTrackingNumber(): void
    {
        $order = $this->makeOrder(['tracking_number' => '999888777666']);

        $this->service->sendStatusUpdateEmail($order, $this->makeBusiness(), 'Delayed');

        $this->assertNotNull($this->service->lastBody);
        $payload = json_decode($this->service->lastBody, true);
        $this->assertIsArray($payload);

        // Subject must contain the tracking number
        $this->assertStringContainsString('999888777666', $payload['content']['subject']);
    }

    public function testSendStatusUpdateEmailBodyHasCorrectStructure(): void
    {
        $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'Out for Delivery'
        );

        $payload = json_decode($this->service->lastBody, true);

        $this->assertArrayHasKey('recipients', $payload);
        $this->assertArrayHasKey('content', $payload);
        $this->assertArrayHasKey('to', $payload['recipients']);
        $this->assertNotEmpty($payload['recipients']['to']);
        $this->assertArrayHasKey('subject', $payload['content']);
        $this->assertArrayHasKey('plainText', $payload['content']);
        $this->assertArrayHasKey('html', $payload['content']);
    }

    public function testSendStatusUpdateEmailAddressesCorrectRecipient(): void
    {
        $business = $this->makeBusiness(['contact_email' => 'logistics@example.com']);

        $this->service->sendStatusUpdateEmail($this->makeOrder(), $business, 'Delivered');

        $payload   = json_decode($this->service->lastBody, true);
        $recipient = $payload['recipients']['to'][0]['email'];
        $this->assertSame('logistics@example.com', $recipient);
    }

    public function testSendStatusUpdateEmailSubjectContainsStatus(): void
    {
        $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'Exception'
        );

        $payload = json_decode($this->service->lastBody, true);
        $this->assertStringContainsString('Exception', $payload['content']['subject']);
    }

    public function testSendStatusUpdateEmailPlainTextContainsRoute(): void
    {
        $order = $this->makeOrder(['origin' => 'Louisville, KY', 'destination' => 'Dallas, TX']);

        $this->service->sendStatusUpdateEmail($order, $this->makeBusiness(), 'In Transit');

        $payload = json_decode($this->service->lastBody, true);
        $this->assertStringContainsString('Louisville, KY', $payload['content']['plainText']);
        $this->assertStringContainsString('Dallas, TX', $payload['content']['plainText']);
    }

    public function testSendStatusUpdateEmailReturnsFalseWhenPostFails(): void
    {
        $this->service->postReturn = false;

        $result = $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'In Transit'
        );

        $this->assertFalse($result);
    }

    public function testSendStatusUpdateEmailSenderIsConfiguredAddress(): void
    {
        $_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'shipping@fedex.com';
        $service = new TestableEmailService();

        $service->sendStatusUpdateEmail($this->makeOrder(), $this->makeBusiness(), 'Delivered');

        $payload = json_decode($service->lastBody, true);
        $this->assertSame('shipping@fedex.com', $payload['sender']);
    }

    public function testSendStatusUpdateEmailWithEventDescription(): void
    {
        $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'Delayed',
            'Weather delay in Memphis area'
        );

        $payload = json_decode($this->service->lastBody, true);
        $this->assertStringContainsString('Weather delay in Memphis area', $payload['content']['plainText']);
        $this->assertStringContainsString('Weather delay in Memphis area', $payload['content']['html']);
    }

    public function testSendStatusUpdateEmailWithEmptyEventDescription(): void
    {
        $this->service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'In Transit',
            ''
        );

        $payload = json_decode($this->service->lastBody, true);
        $this->assertStringContainsString('Status updated to In Transit', $payload['content']['plainText']);
    }

    public function testSendStatusUpdateEmailHtmlContainsBusinessName(): void
    {
        $business = $this->makeBusiness(['name' => 'Global Logistics Inc']);

        $this->service->sendStatusUpdateEmail($this->makeOrder(), $business, 'Delivered');

        $payload = json_decode($this->service->lastBody, true);
        $this->assertStringContainsString('Global Logistics Inc', $payload['content']['html']);
    }

    public function testBuildSignatureProducesValidHmac(): void
    {
        $ref = new \ReflectionMethod($this->service, 'buildSignature');
        $ref->setAccessible(true);

        $signature = $ref->invoke(
            $this->service,
            'POST',
            '/emails:send?api-version=2021-10-01-preview',
            'Mon, 01 Jan 2026 00:00:00 GMT',
            'test.communication.azure.com',
            base64_encode(hash('sha256', '{}', true))
        );

        $this->assertIsString($signature);
        $this->assertNotEmpty($signature);
        // Signature is base64-encoded, so it should decode without errors
        $this->assertNotFalse(base64_decode($signature, true));
    }

    public function testBuildSignatureIsDeterministic(): void
    {
        $ref = new \ReflectionMethod($this->service, 'buildSignature');
        $ref->setAccessible(true);

        $args = [
            'POST',
            '/emails:send',
            'Mon, 01 Jan 2026 00:00:00 GMT',
            'test.communication.azure.com',
            'abc123',
        ];

        $sig1 = $ref->invoke($this->service, ...$args);
        $sig2 = $ref->invoke($this->service, ...$args);

        $this->assertSame($sig1, $sig2);
    }

    public function testRealPostReturnsFalseOnCurlError(): void
    {
        // Use an invalid endpoint to trigger a curl DNS resolution error
        $_ENV['AZURE_EMAIL_CONNECTION_STRING'] =
            'endpoint=https://nonexistent.invalid;accesskey=' . base64_encode('test-key');
        $_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'test@test.com';

        $service = new EmailService(); // Real EmailService, not testable subclass

        $result = $service->sendStatusUpdateEmail(
            ['tracking_number' => 'TRK001', 'origin' => 'A', 'destination' => 'B'],
            ['contact_email' => 'test@test.com', 'name' => 'Test Corp'],
            'In Transit'
        );

        $this->assertFalse($result);
    }

    public function testParseConnectionStringHandlesMissingParts(): void
    {
        $_ENV['AZURE_EMAIL_CONNECTION_STRING'] = '';
        $_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'test@test.com';

        // Constructor should not throw even with empty connection string
        $service = new TestableEmailService();

        // Sending should still work (post is overridden), endpoint/key will be empty
        $result = $service->sendStatusUpdateEmail(
            $this->makeOrder(),
            $this->makeBusiness(),
            'In Transit'
        );
        $this->assertTrue($result);
    }
}
