import { TestBed, ComponentFixture } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { InsightsComponent } from './insights.component';
import { InsightsService } from '../services/insights.service';

describe('InsightsComponent', () => {
  let fixture: ComponentFixture<InsightsComponent>;
  let component: InsightsComponent;
  let mockInsightsService: { getDeliveryInsights: ReturnType<typeof vi.fn> };

  const mockInsights = {
    avg_delivery_time_by_service: [
      { service_type: 'Overnight', avg_hours: 18 },
      { service_type: 'Express', avg_hours: 42 },
      { service_type: 'Ground', avg_hours: 96 },
      { service_type: 'International', avg_hours: 144 },
    ],
    on_time_percentage: 87.5,
    delivery_volume_30d: [
      { date: '2026-04-01', count: 31 },
      { date: '2026-04-04', count: 24 },
    ],
    top_routes: [
      { origin: 'Memphis, TN', destination: 'New York, NY', count: 142 },
    ],
    delay_breakdown: [
      { reason: 'Weather', count: 35 },
      { reason: 'Address Issue', count: 22 },
    ],
  };

  beforeEach(async () => {
    mockInsightsService = {
      getDeliveryInsights: vi.fn(),
    };
    mockInsightsService.getDeliveryInsights.mockReturnValue(of(mockInsights));

    await TestBed.configureTestingModule({
      imports: [InsightsComponent],
      providers: [
        { provide: InsightsService, useValue: mockInsightsService },
      ],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(InsightsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load insights on init', () => {
    expect(component.insights).toEqual(mockInsights);
    expect(component.loading).toBe(false);
  });

  it('should build bar chart data from insights', () => {
    expect(component.barChartData.labels).toEqual(['Overnight', 'Express', 'Ground', 'International']);
    expect(component.barChartData.datasets[0].data).toEqual([18, 42, 96, 144]);
  });

  it('should build line chart data from delivery volume', () => {
    expect(component.lineChartData.labels).toContain('2026-04-01');
    expect(component.lineChartData.datasets[0].data).toContain(31);
  });

  it('should build doughnut chart data from delay breakdown', () => {
    expect(component.doughnutChartData.labels).toContain('Weather');
    expect(component.doughnutChartData.datasets[0].data).toContain(35);
  });

  it('should return green onTimeColor for >= 90%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 92 };
    expect(component.onTimeColor).toBe('#155724');
  });

  it('should return yellow onTimeColor for 70-89%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 87.5 };
    expect(component.onTimeColor).toBe('#856404');
  });

  it('should return red onTimeColor for < 70%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 60 };
    expect(component.onTimeColor).toBe('#721c24');
  });

  it('should return green onTimeBg for >= 90%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 95 };
    expect(component.onTimeBg).toBe('#d4edda');
  });

  it('should return yellow onTimeBg for 70-89%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 80 };
    expect(component.onTimeBg).toBe('#fff3cd');
  });

  it('should return red onTimeBg for < 70%', () => {
    component.insights = { ...mockInsights, on_time_percentage: 65 };
    expect(component.onTimeBg).toBe('#f8d7da');
  });

  it('should return zero values for onTimeColor when no insights loaded', () => {
    component.insights = null;
    expect(component.onTimeColor).toBe('#721c24');
    expect(component.onTimeBg).toBe('#f8d7da');
  });
});
