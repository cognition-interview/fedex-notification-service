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

    protected function setUp(): void
    {
        $_ENV['AZURE_EMAIL_CONNECTION_STRING'] =
            'endpoint=https://test.communication.azure.com;accesskey=' . base64_encode('test-access-key');
        $_ENV['AZURE_EMAIL_FROM_ADDRESS'] = 'noreply@fedex-test.com';

        $this->service = new TestableEmailService();
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
}
