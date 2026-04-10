import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { InsightsService } from '../services/insights.service';
import { DeliveryInsights } from '../models/insight.model';
import { ChartData, ChartOptions } from 'chart.js';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

@Component({
  selector: 'app-insights',
  templateUrl: './insights.component.html',
  styleUrls: ['./insights.component.scss'],
})
export class InsightsComponent implements OnInit {
  insights: DeliveryInsights | null = null;
  loading = true;

  barChartData: ChartData<'bar'> = { labels: [], datasets: [] };
  barChartOptions: ChartOptions<'bar'> = {
    responsive: true,
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: {
      x: { title: { display: true, text: 'Avg Hours' } },
    },
  };

  lineChartData: ChartData<'line'> = { labels: [], datasets: [] };
  lineChartOptions: ChartOptions<'line'> = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, title: { display: true, text: 'Deliveries' } },
    },
  };

  doughnutChartData: ChartData<'doughnut'> = { labels: [], datasets: [] };
  doughnutChartOptions: ChartOptions<'doughnut'> = {
    responsive: true,
    plugins: {
      legend: { position: 'right' },
    },
  };

  constructor(
    private insightsService: InsightsService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.insightsService.getDeliveryInsights().subscribe(data => {
      this.insights = data;
      this.buildCharts(data);
      this.loading = false;
      this.cdr.detectChanges();
    });
  }

  private buildCharts(data: DeliveryInsights): void {
    this.barChartData = {
      labels: data.avg_delivery_time_by_service.map(d => d.service_type),
      datasets: [{
        data: data.avg_delivery_time_by_service.map(d => d.avg_hours),
        backgroundColor: ['#4d148c', '#ff6200', '#004085', '#155724'],
        borderWidth: 0,
      }],
    };

    this.lineChartData = {
      labels: data.delivery_volume_30d.map(d => d.date),
      datasets: [{
        data: data.delivery_volume_30d.map(d => d.count),
        borderColor: '#4d148c',
        backgroundColor: 'rgba(77,20,140,0.1)',
        tension: 0.3,
        fill: true,
        pointBackgroundColor: '#ff6200',
        pointRadius: 4,
      }],
    };

    this.doughnutChartData = {
      labels: data.delay_breakdown.map(d => d.reason),
      datasets: [{
        data: data.delay_breakdown.map(d => d.count),
        backgroundColor: ['#4d148c', '#ff6200', '#dc3545', '#ffc107', '#6c757d'],
        borderWidth: 1,
      }],
    };
  }

  get onTimeColor(): string {
    const pct = this.insights?.on_time_percentage ?? 0;
    if (pct >= 90) return '#155724';
    if (pct >= 70) return '#856404';
    return '#721c24';
  }

  get onTimeBg(): string {
    const pct = this.insights?.on_time_percentage ?? 0;
    if (pct >= 90) return '#d4edda';
    if (pct >= 70) return '#fff3cd';
    return '#f8d7da';
  }
}
